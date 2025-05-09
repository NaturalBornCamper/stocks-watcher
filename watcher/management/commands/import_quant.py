import csv
import re
import traceback
from datetime import datetime

from django.core.management.base import BaseCommand

from utils.quant import find_matching_value, Columns, COLUMN_NAME_VARIANTS
from watcher.models import Quant, QuantStock


# python manage.py import_quant /path/to/your/csv_file.csv
# python manage.py import_quant "Quant Dumps/2025-02.csv"
# python manage.py import_quant "organized_quant/2025-02-01.csv"


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

                quant_list = []
                error = False
                for row in csv_reader:
                    quant = Quant()

                    # Convert row to use standardized column names
                    new_row = {}
                    for col_name, possible_names in COLUMN_NAME_VARIANTS.items():
                        new_row[col_name] = find_matching_value(row, possible_names)

                    # If no date in column, use current date
                    quant.quant_stock, created = QuantStock.objects.get_or_create(
                        symbol=new_row[Columns.SEEKINGALPHA_SYMBOL],
                        defaults={"name": new_row[Columns.COMPANY_NAME]}
                    )
                    quant.date = new_row[Columns.DATE] if new_row[Columns.DATE] else datetime.today()
                    quant.type = new_row[Columns.TYPE]
                    quant.rank = new_row[Columns.RANK]
                    quant.quant = clean(new_row[Columns.QUANT])
                    quant.rating_seeking_alpha = clean(new_row[Columns.RATING_SEEKING_ALPHA])
                    quant.rating_wall_street = clean(new_row[Columns.RATING_WALL_STREET])
                    quant.market_cap_millions = convert_market_cap_to_millions(
                        new_row[Columns.MARKET_CAP_MILLIONS], new_row[Columns.SEEKINGALPHA_SYMBOL]
                    )
                    quant.dividend_yield = clean(new_row[Columns.DIVIDEND_YIELD])
                    quant.valuation = new_row[Columns.VALUATION]
                    quant.profitability = new_row[Columns.PROFITABILITY]
                    quant.growth = new_row[Columns.GROWTH]
                    quant.momentum = new_row[Columns.MOMENTUM]
                    quant.eps_revision = new_row[Columns.EPS_REVISION]

                    if BULK_INSERTION:
                        quant_list.append(quant)
                    else:
                        try:
                            quant.save()
                        except Exception as e:
                            print("ERROR SAVING QUANT VALUES")
                            print(quant.date)
                            print(quant.type)
                            print(quant.rank)
                            print(quant.quant_stock.symbol)
                            print(quant.quant)
                            print(quant.rating_seeking_alpha)
                            print(quant.rating_wall_street)
                            print(quant.market_cap_millions)
                            print(quant.dividend_yield)
                            print(quant.valuation)
                            print(quant.profitability)
                            print(quant.growth)
                            print(quant.momentum)
                            print(quant.eps_revision)
                            print(e)
                            traceback.print_exc()
                            error = True

                if BULK_INSERTION:
                    Quant.objects.bulk_create(quant_list, ignore_conflicts=True)

                if not error:
                    self.stdout.write(self.style.SUCCESS("Data imported successfully."))

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"File not found: {csv_file}"))