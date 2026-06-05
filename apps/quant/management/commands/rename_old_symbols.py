from django.core.management.base import BaseCommand

from apps.quant.symbols.dumps import (
    SA_DUMPS_FOLDER, find_dated_dump_files, find_dump_files, find_column, read_dump, write_dump,
)
from apps.quant.symbols.matching import is_share_class_pair
from utils.quant import Columns

# python manage.py rename_old_symbols


class Command(BaseCommand):
    help = (
        "Make the old dumps use today's tickers. The newest monthly dump is the "
        "truth (ticker + permanent SEC id per company); any older row where the "
        "same company (same CIK) appears under a different ticker gets renamed in "
        "every dump file. Share-class pairs (GOOG/GOOGL, BRK.A/BRK.B) are kept "
        "apart, and rows without a CIK are left for manual review at import."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "folder", type=str, nargs="?", default=SA_DUMPS_FOLDER,
            help=f"Folder containing the dump CSVs (default: {SA_DUMPS_FOLDER})",
        )

    def handle(self, *args, **options):
        dated = find_dated_dump_files(options["folder"])
        if not dated:
            self.stderr.write(self.style.ERROR(f"No dated dump files found in {options['folder']}."))
            return
        latest = dated[-1]

        current, ambiguous = self.load_current_identities(latest)
        self.stdout.write(f"Reference: {latest.name} ({len(current)} stocks with a CIK)")
        if ambiguous:
            self.stdout.write(
                f"  Skipping {len(ambiguous)} CIK(s) listed under several tickers in the newest dump (share classes)."
            )

        # Pass 1: compare every older row against the current identities to find
        # the tickers that changed. Each rename remembers its CIK so a recycled
        # ticker (another company later using the same letters) is never touched.
        renames = {}  # old_symbol -> (cik, new_symbol, new_name)
        kept_share_classes = set()
        for csv_file in find_dump_files(options["folder"]):
            if csv_file == latest:
                continue
            fieldnames, rows = read_dump(csv_file)
            if not fieldnames or Columns.CIK not in fieldnames:
                continue
            symbol_col = find_column(fieldnames, Columns.SEEKINGALPHA_SYMBOL)
            if not symbol_col:
                continue

            for row in rows:
                cik = (row.get(Columns.CIK) or "").strip()
                symbol = (row.get(symbol_col) or "").strip()
                if not cik or cik in ambiguous or cik not in current:
                    continue
                new_symbol, new_name = current[cik]
                if symbol == new_symbol or symbol in renames:
                    continue
                if is_share_class_pair(symbol, new_symbol):
                    kept_share_classes.add(f"{symbol}/{new_symbol}")
                    continue
                renames[symbol] = (cik, new_symbol, new_name)
                self.stdout.write(f"  RENAME {symbol} -> {new_symbol} ({new_name})")

        for pair in sorted(kept_share_classes):
            self.stdout.write(f"  KEEP   {pair} (share classes of one company)")

        if not renames:
            self.stdout.write(self.style.SUCCESS("All dumps already use the current tickers."))
            return

        # Pass 2: apply the renames to every dump file
        files_changed = 0
        rows_renamed = 0
        for csv_file in find_dump_files(options["folder"]):
            fieldnames, rows = read_dump(csv_file)
            if not fieldnames:
                continue
            symbol_col = find_column(fieldnames, Columns.SEEKINGALPHA_SYMBOL)
            name_col = find_column(fieldnames, Columns.COMPANY_NAME)
            if not symbol_col:
                continue

            changed = 0
            for row in rows:
                symbol = (row.get(symbol_col) or "").strip()
                if symbol not in renames:
                    continue
                cik, new_symbol, new_name = renames[symbol]
                # Only rename when the row is the same company (or predates the
                # CIK column) -- protects against recycled tickers
                row_cik = (row.get(Columns.CIK) or "").strip()
                if row_cik not in ("", cik):
                    continue
                row[symbol_col] = new_symbol
                if name_col and new_name:
                    row[name_col] = new_name
                changed += 1

            if changed:
                write_dump(csv_file, fieldnames, rows)
                files_changed += 1
                rows_renamed += changed

        self.stdout.write(self.style.SUCCESS(
            f"Renamed {len(renames)} ticker(s) across {files_changed} file(s) ({rows_renamed} rows)."
        ))

    def load_current_identities(self, latest_file):
        """Read the newest dump into {cik: (symbol, name)}. A CIK that shows up
        under two different tickers there (share classes trading side by side)
        goes into the ambiguous set and is excluded from renaming."""
        fieldnames, rows = read_dump(latest_file)
        symbol_col = find_column(fieldnames, Columns.SEEKINGALPHA_SYMBOL)
        name_col = find_column(fieldnames, Columns.COMPANY_NAME)

        current = {}
        ambiguous = set()
        for row in rows:
            cik = (row.get(Columns.CIK) or "").strip()
            symbol = (row.get(symbol_col) or "").strip()
            if not cik or not symbol:
                continue
            if cik in current and current[cik][0] != symbol:
                ambiguous.add(cik)
            else:
                current.setdefault(cik, (symbol, (row.get(name_col) or "").strip()))
        return current, ambiguous
