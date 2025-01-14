import csv
import re
import traceback
from datetime import datetime

from django.core.management.base import BaseCommand

from watcher.models import Quant, QuantStock

# python manage.py import_quant /path/to/your/csv_file.csv
# python manage.py import_quant "Quant Dumps/2024-01.csv"


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
    # Remove leading and trailing whitespaces
    string_value = string_value.strip()

    for clip in EXCLUSION_LIST:
        string_value = re.sub(clip, '', string_value, flags=re.IGNORECASE)
        # string_value = string_value.replace(clip, "")

    if string_value == "-" or string_value == "":
        string_value = None

    return string_value


class Command(BaseCommand):
    DATE = 0
    TYPE = 1
    RANK = 2
    SEEKINGALPHA_SYMBOL = 3
    COMPANY_NAME = 4
    QUANT = 5
    RATING_SEEKING_ALPHA = 6
    RATING_WALL_STREET = 7
    MARKET_CAP_MILLIONS = 8
    DIVIDEND_YIELD = 9
    VALUATION = 10
    GROWTH = 11
    PROFITABILITY = 12
    MOMENTUM = 13
    EPS_REVISION = 14

    help = 'Import data from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file')

    def handle(self, *args, **options):
        csv_file = options['csv_file']

        try:
            with open(csv_file, 'r') as file:
                csv_reader = csv.reader(file)
                # Skip header row
                next(csv_reader)

                quant_list = []
                error = False
                for row in csv_reader:
                    quant = Quant()

                    # If no date in column, use current date
                    quant.quant_stock, created = QuantStock.objects.get_or_create(
                        symbol=row[self.SEEKINGALPHA_SYMBOL],
                        defaults={"name": row[self.COMPANY_NAME]}
                    )
                    quant.date = row[self.DATE] if row[self.DATE] else datetime.today()
                    quant.type = row[self.TYPE]
                    quant.rank = row[self.RANK]
                    quant.quant = clean(row[self.QUANT])
                    quant.rating_seeking_alpha = clean(row[self.RATING_SEEKING_ALPHA])
                    quant.rating_wall_street = clean(row[self.RATING_WALL_STREET])
                    quant.market_cap_millions = convert_market_cap_to_millions(
                        row[self.MARKET_CAP_MILLIONS], row[self.SEEKINGALPHA_SYMBOL]
                    )
                    quant.dividend_yield = clean(row[self.DIVIDEND_YIELD])
                    quant.valuation = row[self.VALUATION]
                    quant.profitability = row[self.PROFITABILITY]
                    quant.growth = row[self.GROWTH]
                    quant.momentum = row[self.MOMENTUM]
                    quant.eps_revision = row[self.EPS_REVISION]

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
