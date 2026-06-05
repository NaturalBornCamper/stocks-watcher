import csv
import pathlib
import re
import traceback
from datetime import datetime

from django.core.management.base import BaseCommand

from utils.quant import find_matching_value, Columns, COLUMN_NAME_VARIANTS
from apps.quant.models import SAStock, SARating
from apps.quant.symbols.edgar import load_ticker_to_cik, normalize_ticker
from apps.quant.symbols.matching import is_share_class_pair

# python manage.py import_sa_ratings /path/to/your/csv_file.csv
# python manage.py import_sa_ratings "SA Rating Dumps/2025-02-01.csv"
# python manage.py import_sa_ratings "data_dumps/seeking_alpha/2025-05-01.csv"
# python manage.py import_sa_ratings "data_dumps/seeking_alpha/*.csv"


EXCLUSION_LIST = [
    "rating: strong buy",
    "rating: buy",
    "rating: hold",
    "rating: sell",
    "rating: strong sell",
    "rating: not covered",
    "%"
]

BULK_INSERTION = True


# Converts values like 1.2B to 1200M
def convert_market_cap_to_millions(string_value: str, symbol: str) -> float | None:
    if not string_value:
        return None

    match string_value[-1].upper():
        case "K":
            multiplier = 0.001
        case "M":
            multiplier = 1
        case "M":
            multiplier = 1
        case "B":
            multiplier = 1000
        case "T":
            multiplier = 1000000
        case _:
            raise Exception(
                f"Market cap for {symbol} has an unknown value: \"{string_value}\". Expected suffixes are K/M/B/T"
            )

    return float(string_value[:-1]) * multiplier


# Remove percentage symbol, useless strings, make sure the empty value "-" is replaced
def clean(string_value: str) -> str | None:
    for clip in EXCLUSION_LIST:
        string_value = re.sub(clip, "", string_value, flags=re.IGNORECASE)

    # Remove leading and trailing whitespaces
    string_value = string_value.strip()

    if string_value == "-" or string_value == "":
        string_value = None

    return string_value


class Command(BaseCommand):
    help = 'Import data from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    def handle(self, *args, **options):
        files_to_import = []
        # If csv_file has a wildcard, use glob to find all matching files
        if "*" in options['csv_file']:
            path = pathlib.Path(options['csv_file'])
            base_dir = path.parent
            pattern = path.name
            # Sort so dumps import oldest-first; this lets us spot a company that
            # changed ticker (its old symbol is already in the DB by then). Skip
            # "_"-prefixed helper/cache files.
            files_to_import = sorted(f for f in base_dir.rglob(pattern) if not f.name.startswith("_"))
        else:
            files_to_import.append(options['csv_file'])

        # SEC ticker -> CIK map, used when a dump row has no CIK column of its own
        ticker_to_cik = load_ticker_to_cik()
        # Warn only once per ticker when a dump's CIK contradicts the stored one
        self.cik_mismatch_warned = set()

        files_imported = 0
        for csv_file in files_to_import:
            try:
                with open(csv_file, 'r', encoding='utf-8') as file:
                    csv_reader = csv.DictReader(file)

                    sa_ratings_list = []
                    error = False
                    for row in csv_reader:
                        sa_rating = SARating()

                        # Convert row to use standardized column names
                        new_row = {}
                        for col_name, possible_names in COLUMN_NAME_VARIANTS.items():
                            new_row[col_name] = find_matching_value(row, possible_names)

                        sa_rating.sa_stock = self.find_or_update_stock(new_row, ticker_to_cik)

                        # If no date in column, use current date
                        sa_rating.date = new_row[Columns.DATE] if new_row[Columns.DATE] else datetime.today()
                        sa_rating.type = new_row[Columns.TYPE]
                        sa_rating.rank = new_row[Columns.RANK]
                        sa_rating.quant = clean(new_row[Columns.QUANT])
                        sa_rating.rating_seeking_alpha = clean(new_row[Columns.RATING_SEEKING_ALPHA])
                        sa_rating.rating_wall_street = clean(new_row[Columns.RATING_WALL_STREET])
                        sa_rating.market_cap_millions = convert_market_cap_to_millions(
                            new_row[Columns.MARKET_CAP_MILLIONS], new_row[Columns.SEEKINGALPHA_SYMBOL]
                        )
                        sa_rating.dividend_yield = clean(new_row[Columns.DIVIDEND_YIELD])
                        sa_rating.valuation = new_row[Columns.VALUATION]
                        sa_rating.profitability = new_row[Columns.PROFITABILITY]
                        sa_rating.growth = new_row[Columns.GROWTH]
                        sa_rating.momentum = new_row[Columns.MOMENTUM]
                        sa_rating.eps_revision = new_row[Columns.EPS_REVISION]

                        if BULK_INSERTION:
                            sa_ratings_list.append(sa_rating)
                        else:
                            try:
                                sa_rating.save()
                            except Exception as e:
                                print("ERROR SAVING SEEKING ALPHA RATINGS")
                                print(sa_rating.date)
                                print(sa_rating.type)
                                print(sa_rating.rank)
                                print(sa_rating.sa_stock.symbol)
                                print(sa_rating.quant)
                                print(sa_rating.rating_seeking_alpha)
                                print(sa_rating.rating_wall_street)
                                print(sa_rating.market_cap_millions)
                                print(sa_rating.dividend_yield)
                                print(sa_rating.valuation)
                                print(sa_rating.profitability)
                                print(sa_rating.growth)
                                print(sa_rating.momentum)
                                print(sa_rating.eps_revision)
                                print(e)
                                traceback.print_exc()
                                error = True

                    if BULK_INSERTION:
                        SARating.objects.bulk_create(sa_ratings_list, ignore_conflicts=True)

                    if not error:
                        files_imported += 1
                        self.stdout.write(self.style.SUCCESS(f"{csv_file} imported successfully."))

            except FileNotFoundError:
                self.stderr.write(self.style.ERROR(f"File not found: {csv_file}"))

        if files_imported == 0:
            self.stderr.write(self.style.ERROR("No files imported."))
        else:
            self.stdout.write(self.style.SUCCESS(f"{files_imported} files imported."))

    def find_or_update_stock(self, new_row, ticker_to_cik):
        """Find the stock a dump row belongs to, following ticker changes.

        Match by ticker first. If the ticker is unknown but the row's permanent
        SEC id (CIK) belongs to exactly one stock we already track -- and the
        two tickers are not just share classes of one company -- then the
        company changed ticker: rename the existing stock in place so all its
        history stays attached. Rows without a CIK can only match by ticker
        (the best we can do); an unseen ticker there becomes a new stock."""
        symbol = new_row[Columns.SEEKINGALPHA_SYMBOL]
        name = new_row[Columns.COMPANY_NAME]
        # Cleaned dumps carry the CIK in their own column; fall back to a lookup
        # in the SEC mapping for dumps that were not stamped yet
        cik = new_row[Columns.CIK].strip() or ticker_to_cik.get(normalize_ticker(symbol), "")

        sa_stock = SAStock.objects.filter(symbol=symbol).first()
        if sa_stock:
            # Fill in a missing permanent id, but never switch an existing one:
            # a different id would mean another company reused this ticker
            if cik and not sa_stock.external_id:
                sa_stock.external_id = cik
                sa_stock.save()
            elif cik and sa_stock.external_id != cik and symbol not in self.cik_mismatch_warned:
                self.cik_mismatch_warned.add(symbol)
                self.stdout.write(self.style.WARNING(
                    f"  {symbol}: dump says CIK {cik} but stock has {sa_stock.external_id}"
                    " - ticker reused by another company?"
                ))
            return sa_stock

        # Unknown ticker: see if the permanent id points to a stock we already track
        if cik:
            same_company = list(SAStock.objects.filter(external_id=cik)[:2])
            if len(same_company) == 1 and not is_share_class_pair(symbol, same_company[0].symbol):
                # Same company, a single candidate, not a share class: rename it
                # in place and keep all its ratings history attached
                sa_stock = same_company[0]
                old_symbol = sa_stock.symbol
                sa_stock.symbol = symbol
                sa_stock.name = name
                sa_stock.save()
                self.stdout.write(f"  Ticker change: {old_symbol} -> {symbol} ({name})")
                return sa_stock

        # Genuinely new stock (or one we cannot match without a CIK)
        return SAStock.objects.create(symbol=symbol, name=name, external_id=cik)