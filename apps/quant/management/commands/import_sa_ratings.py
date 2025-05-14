import csv
import re
import traceback
from datetime import datetime

from django.core.management.base import BaseCommand

from utils.quant import find_matching_value, Columns, COLUMN_NAME_VARIANTS
from apps.quant.models import SAStock, SARating

# python manage.py import_sa_ratings /path/to/your/csv_file.csv
# python manage.py import_sa_ratings "SA Rating Dumps/2025-02-01.csv"
# python manage.py import_sa_ratings "data_dumps/seeking_alpha/2025-05-01.csv"


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
        csv_file = options['csv_file']

        try:
            with open(csv_file, 'r') as file:
                csv_reader = csv.DictReader(file)

                sa_ratings_list = []
                error = False
                for row in csv_reader:
                    sa_rating = SARating()

                    # Convert row to use standardized column names
                    new_row = {}
                    for col_name, possible_names in COLUMN_NAME_VARIANTS.items():
                        new_row[col_name] = find_matching_value(row, possible_names)

                    # If no date in column, use current date
                    sa_rating.sa_stock, created = SAStock.objects.get_or_create(
                        symbol=new_row[Columns.SEEKINGALPHA_SYMBOL],
                        defaults={"name": new_row[Columns.COMPANY_NAME]}
                    )
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
                    self.stdout.write(self.style.SUCCESS("Data imported successfully."))

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"File not found: {csv_file}"))