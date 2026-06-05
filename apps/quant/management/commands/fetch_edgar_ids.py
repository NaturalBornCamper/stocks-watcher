import pathlib

from django.core.management.base import BaseCommand

from apps.quant.symbols.dumps import (
    SA_DUMPS_FOLDER, find_dated_dump_files, find_column, read_dump, write_dump,
)
from apps.quant.symbols.edgar import load_ticker_to_cik, normalize_ticker
from utils.quant import Columns

# python manage.py fetch_edgar_ids                                          (newest monthly dump)
# python manage.py fetch_edgar_ids "data_dumps/seeking_alpha/2025-05-01.csv"  (one specific file)


class Command(BaseCommand):
    help = (
        "Fetch each stock's permanent SEC id (CIK) and save it into a dump CSV "
        "as a CIK column. Works on the newest monthly dump by default, or on one "
        "specific file passed by name. An already-stamped CIK is never blanked, "
        "so delisted tickers keep the id they had."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_file", type=str, nargs="?",
            help=f"One dump CSV to stamp (default: the newest monthly dump in {SA_DUMPS_FOLDER})",
        )

    def handle(self, *args, **options):
        ticker_to_cik = load_ticker_to_cik()
        if not ticker_to_cik:
            self.stderr.write(self.style.ERROR("Could not load the SEC CIK mapping; nothing stamped."))
            return

        # Work out which file to stamp: the one given by name, or the newest monthly dump
        if options["csv_file"]:
            csv_file = pathlib.Path(options["csv_file"])
            if not csv_file.exists():
                self.stderr.write(self.style.ERROR(f"File not found: {csv_file}"))
                return
        else:
            dated = find_dated_dump_files()
            if not dated:
                self.stderr.write(self.style.ERROR(f"No dated dump files found in {SA_DUMPS_FOLDER}."))
                return
            csv_file = dated[-1]

        fieldnames, rows = read_dump(csv_file)
        if not fieldnames:
            self.stderr.write(self.style.ERROR(f"{csv_file.name} is empty."))
            return
        symbol_col = find_column(fieldnames, Columns.SEEKINGALPHA_SYMBOL)
        if not symbol_col:
            self.stderr.write(self.style.ERROR(f"{csv_file.name} has no symbol column."))
            return

        # Add the CIK column at the end if this file doesn't have one yet
        changed = False
        if Columns.CIK not in fieldnames:
            fieldnames = fieldnames + [Columns.CIK]
            changed = True

        # Look up every row's ticker in the SEC mapping and write the id in
        stamped = 0
        for row in rows:
            symbol = (row.get(symbol_col) or "").strip()
            cik = ticker_to_cik.get(normalize_ticker(symbol), "")

            # Only ever fill or correct -- never blank an id we already have
            if cik and (row.get(Columns.CIK) or "") != cik:
                row[Columns.CIK] = cik
                changed = True
            if cik or (row.get(Columns.CIK) or ""):
                stamped += 1

        # Skip the write when nothing moved, so re-runs leave no git noise
        if changed:
            write_dump(csv_file, fieldnames, rows)

        self.stdout.write(self.style.SUCCESS(
            f"{csv_file.name}: CIK on {stamped}/{len(rows)} rows"
            + ("" if changed else " (already up to date, file untouched)")
        ))
