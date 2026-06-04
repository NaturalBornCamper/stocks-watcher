import csv
import pathlib

from django.core.management.base import BaseCommand

from apps.quant.edgar import load_ticker_to_cik, normalize_ticker
from utils.quant import Columns, COLUMN_NAME_VARIANTS

# python manage.py clean_dumps "data_dumps/seeking_alpha/_symbol_renames.csv"
# python manage.py clean_dumps "data_dumps/seeking_alpha/_symbol_renames.csv" "data_dumps/seeking_alpha/*.csv"


class Command(BaseCommand):
    help = (
        "Rewrite the SA dump CSVs so a company that changed ticker keeps one symbol. "
        "Reads a renames file (old_symbol,new_symbol,old_name,new_name,...) produced by "
        "find_symbol_changes and replaces the old symbol (and company name) with the "
        "canonical one in every dump. Run it on dev, then commit the cleaned CSVs."
    )

    def add_arguments(self, parser):
        parser.add_argument("renames_file", type=str, help="CSV of renames to apply")
        parser.add_argument(
            "dumps", type=str, nargs="?", default="data_dumps/seeking_alpha/*.csv",
            help="Glob of dump CSVs to clean (default: data_dumps/seeking_alpha/*.csv)",
        )
        parser.add_argument(
            "--keep-names", action="store_true",
            help="Only change the ticker symbol; leave the company name as it is.",
        )

    def handle(self, *args, **options):
        renames = self.load_renames(options["renames_file"])
        self.stdout.write(f"Loaded {len(renames)} rename(s).")

        # The permanent SEC id (CIK) we stamp into every row comes from this map.
        ticker_to_cik = load_ticker_to_cik()
        if not ticker_to_cik:
            self.stderr.write(self.style.WARNING(
                "Could not load the SEC CIK mapping; the CIK column will be left blank."
            ))

        glob_path = pathlib.Path(options["dumps"])
        files = sorted(glob_path.parent.rglob(glob_path.name))

        # Never rewrite the renames file or the EDGAR cache, even if the glob catches them
        skip_names = {pathlib.Path(options["renames_file"]).name, "_edgar_company_tickers.json"}

        files_changed = 0
        rows_renamed = 0
        for csv_file in files:
            if csv_file.name in skip_names:
                continue
            renamed = self.clean_one_file(csv_file, renames, ticker_to_cik, options["keep_names"])
            if renamed is not None:
                files_changed += 1
                rows_renamed += renamed
                self.stdout.write(f"  {csv_file.name}: rewritten ({renamed} symbol(s) renamed)")

        self.stdout.write(self.style.SUCCESS(
            f"Done. Rewrote {files_changed} file(s); renamed {rows_renamed} row(s); CIK stamped on all rows."
        ))

    def load_renames(self, path):
        """Read the renames CSV into {old_symbol: (new_symbol, new_name)}, following
        chains so that A->B->C resolves straight to C."""
        direct = {}
        names = {}
        with open(path, "r", newline="", encoding="utf-8") as file:
            for row in csv.DictReader(file):
                old = (row.get("old_symbol") or "").strip()
                new = (row.get("new_symbol") or "").strip()
                if old and new and old != new:
                    direct[old] = new
                    names[new] = (row.get("new_name") or "").strip()

        # Follow chains to the final symbol (a "seen" set guards against loops)
        resolved = {}
        for old in direct:
            seen = set()
            current = old
            while current in direct and current not in seen:
                seen.add(current)
                current = direct[current]
            resolved[old] = (current, names.get(current, ""))
        return resolved

    def clean_one_file(self, csv_file, renames, ticker_to_cik, keep_names):
        """Rewrite one dump CSV: swap renamed symbols/names and stamp the SEC CIK
        (permanent company id) onto every row. The file is only rewritten when
        something actually changes. Returns the number of symbols renamed, or
        None if the file was left untouched."""
        with open(csv_file, "r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames
            rows = list(reader)

        if not fieldnames:
            return None

        # Work out which headers hold the symbol and the company name
        symbol_col = next((c for c in COLUMN_NAME_VARIANTS[Columns.SEEKINGALPHA_SYMBOL] if c in fieldnames), None)
        name_col = next((c for c in COLUMN_NAME_VARIANTS[Columns.COMPANY_NAME] if c in fieldnames), None)
        if not symbol_col:
            return None

        # Add a CIK column at the end if the file doesn't have one yet
        changed = False
        if Columns.CIK not in fieldnames:
            fieldnames = fieldnames + [Columns.CIK]
            changed = True

        renamed = 0
        for row in rows:
            symbol = (row.get(symbol_col) or "").strip()
            if symbol in renames:
                new_symbol, new_name = renames[symbol]
                row[symbol_col] = new_symbol
                if name_col and new_name and not keep_names:
                    row[name_col] = new_name
                symbol = new_symbol
                renamed += 1
                changed = True

            # Stamp the permanent id, looked up by the (now canonical) ticker
            cik = ticker_to_cik.get(normalize_ticker(symbol), "")
            if (row.get(Columns.CIK) or "") != cik:
                row[Columns.CIK] = cik
                changed = True

        if not changed:
            return None

        with open(csv_file, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(rows)
        return renamed