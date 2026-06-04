import csv
import pathlib

from django.core.management.base import BaseCommand
from django.db.models import Max

from apps.quant.models import SAStock
from apps.quant.symbols import SYMBOL_RENAMES_FILE
from apps.quant.symbols.edgar import load_ticker_to_cik, normalize_ticker
from apps.quant.symbols.matching import find_same_company, review_for_match, normalize_company_name

# python manage.py find_symbol_changes
# python manage.py find_symbol_changes --rescan
# python manage.py find_symbol_changes --write-renames               (updates data_dumps/_symbol_renames.csv)
# python manage.py find_symbol_changes --write-renames "other/file.csv"


class Command(BaseCommand):
    help = (
        "Find SA stocks that look like the same company under a new ticker or name "
        "(rename, share class, acquisition) and flag them for review in the admin. "
        "Also stores each stock's SEC CIK. Safe to run on a schedule."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--rescan", action="store_true",
            help="Re-examine stocks that already have a review note (overwrites them). "
                 "By default reviewed stocks are left untouched so your decisions stick.",
        )
        parser.add_argument(
            "--write-renames", dest="write_renames", nargs="?", const=SYMBOL_RENAMES_FILE, metavar="PATH",
            help="Also write the flagged renames to a CSV so you can curate it and "
                 "feed it to the clean_dumps command. New rows are appended; rows already "
                 f"in the file are kept as-is so your edits are not lost. Default: {SYMBOL_RENAMES_FILE}",
        )

    def handle(self, *args, **options):
        ticker_to_cik = load_ticker_to_cik()
        if not ticker_to_cik:
            self.stderr.write(self.style.WARNING(
                "Could not load the SEC CIK mapping; matching will rely on company names only."
            ))

        # Step 1: store the SEC CIK on every stock we can match. This is a plain
        # fact (not a decision), so we update all stocks every run.
        cik_updates = []
        for stock in SAStock.objects.all():
            cik = ticker_to_cik.get(normalize_ticker(stock.symbol), "")
            if cik and cik != stock.external_id:
                stock.external_id = cik
                cik_updates.append(stock)
        if cik_updates:
            SAStock.objects.bulk_update(cik_updates, ["external_id"])
        self.stdout.write(self.style.SUCCESS(f"Set/updated CIK on {len(cik_updates)} stock(s)."))

        # On a rescan, clear all flags first so stocks that no longer match (e.g.
        # after a CIK fix) get un-flagged instead of keeping a stale note.
        if options["rescan"]:
            SAStock.objects.update(needs_review=False, review_note="")

        # Step 2: walk stocks newest-first (by their most recent rating). The first
        # time we meet a company it is via its current ticker, so older tickers that
        # follow get mapped onto that current one -- which matches EDGAR/Yahoo today.
        stocks_by_cik = {}
        stocks_by_name = {}
        flagged = 0
        share_classes = 0
        review_updates = []
        rename_rows = []
        stocks = SAStock.objects.annotate(last_seen=Max("sarating__date")).order_by("-last_seen", "-id")
        for stock in stocks:
            match, matched_by = find_same_company(
                stock.symbol, stock.name, stock.external_id, stocks_by_cik, stocks_by_name
            )
            # Remember this stock for later ones before deciding anything
            if stock.external_id:
                stocks_by_cik.setdefault(stock.external_id, stock)
            stocks_by_name.setdefault(normalize_company_name(stock.name), stock)

            if not match:
                continue
            # Leave stocks we have already looked at alone, unless asked to rescan
            if stock.review_note and not options["rescan"]:
                continue

            needs_review, note = review_for_match(stock.symbol, match.symbol, match.name, matched_by)
            stock.needs_review = needs_review
            stock.review_note = note
            review_updates.append(stock)
            if needs_review:
                flagged += 1
                # `match` is the current (newer) ticker and `stock` is the older
                # alias, so the canonical symbol to keep is match.symbol.
                rename_rows.append({
                    "old_symbol": stock.symbol, "new_symbol": match.symbol,
                    "old_name": stock.name, "new_name": match.name, "matched_by": matched_by,
                })
                self.stdout.write(f"  REVIEW  {stock.symbol} -> {match.symbol}: {note}")
            else:
                share_classes += 1

        if review_updates:
            SAStock.objects.bulk_update(review_updates, ["needs_review", "review_note"])

        if options["write_renames"]:
            added = self.write_renames_file(options["write_renames"], rename_rows)
            self.stdout.write(self.style.SUCCESS(
                f"Wrote renames file {options['write_renames']} (+{added} new row(s))."
            ))

        self.stdout.write(self.style.SUCCESS(
            f"Flagged {flagged} possible symbol change(s); marked {share_classes} share-class pair(s)."
        ))

    def write_renames_file(self, path, rename_rows):
        """Save flagged renames to a CSV for you to curate, then hand to clean_dumps.

        Existing rows are kept exactly as they are (so your manual edits survive);
        only rows whose old_symbol is not already in the file are added. Returns
        how many new rows were added."""
        fieldnames = ["old_symbol", "new_symbol", "old_name", "new_name", "matched_by"]

        # Read whatever is already there so we don't clobber your curation
        existing_rows = []
        existing_old_symbols = set()
        file_path = pathlib.Path(path)
        if file_path.exists():
            with open(file_path, "r", newline="", encoding="utf-8") as file:
                for row in csv.DictReader(file):
                    existing_rows.append(row)
                    existing_old_symbols.add(row.get("old_symbol", ""))

        new_rows = [row for row in rename_rows if row["old_symbol"] not in existing_old_symbols]

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(existing_rows + new_rows)
        return len(new_rows)