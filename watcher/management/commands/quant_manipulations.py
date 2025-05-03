import csv
import pathlib
from datetime import datetime

from django.core.management.base import BaseCommand

from watcher.management.commands.import_quant import Columns, COLUMN_NAMES

# Executes these 3 steps:
#  1-Recursively reads all quant dump csv files from an input folder
#  2-Aggregates them into a single dictionary
#  3-Splits the generated quant data dump dictionary into the different csv files, as requested
# Example usage:
# python manage.py quant_manipulations <function> /path/to/your/csv_dump_folder /path/to/your/output_folder <asc|desc>
# python manage.py quant_manipulations by_date_then_type "Quant Dumps/" organized_quant
# python manage.py quant_manipulations by_type_then_date "Quant Dumps/" organized_quant
# python manage.py quant_manipulations one_csv_per_date "Quant Dumps/" organized_quant asc
# python manage.py quant_manipulations one_csv_per_type "Quant Dumps/" organized_quant desc
# I usually use this one:
#  python manage.py quant_manipulations one_csv_per_date "organized_quant/" organized_quant

# Recursively reads all quant dump csv files in a folder, and aggregates them into a single dictionary
def aggregate_csv_quant_files(input_folder: str, first_key: int, second_key: int = None) -> dict:
    csv_filepaths = pathlib.Path(input_folder).rglob("*.csv")
    quant_dict = {}
    for csv_filepath in csv_filepaths:
        with csv_filepath.open("r") as f:
            csv_reader = csv.reader(f)

            # If csv_reader's current row and first column == "Date", we know it"s a header so skip it
            row = next(csv_reader)  # Read the first row
            if row[Columns.DATE] != COLUMN_NAMES[Columns.DATE]:
                f.seek(0)

            for row in csv_reader:
                if row[first_key] not in quant_dict:
                    quant_dict[row[first_key]] = {} if second_key is not None else []
                if second_key is not None:
                    if row[second_key] not in quant_dict[row[first_key]]:
                        quant_dict[row[first_key]][row[second_key]] = []
                    quant_dict[row[first_key]][row[second_key]].append(row)
                else:
                    quant_dict[row[first_key]].append(row)

    return quant_dict


# Writes a list of lines to a csv file, sorting them if necessary
def write_lines_to_csv_file(lines, output_file: str, sort_order: str) -> None:
    # Sort quant list by their date (asc or desc), then type, then rank
    # date sorting has no effect on multi-levels export (since a folder per date, or a file per date)
    if sort_order == "desc":
        lines.sort(key=lambda x: (-datetime.strptime(x[0], "%Y-%m-%d").timestamp(), x[1], int(x[2])))
    else:
        lines.sort(key=lambda x: (datetime.strptime(x[0], "%Y-%m-%d").timestamp(), x[1], int(x[2])))

    with open(output_file, "w", newline='') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        # Start with header
        writer.writerow(COLUMN_NAMES.values())

        for line in lines:
            writer.writerow(line)


# Splits the generated quant data dump dictionary into the different csv files
def process_quant_for_output(quant_dict: dict, output_folder: str, sort_order: str) -> None:
    pathlib.Path(output_folder).mkdir(parents=True, exist_ok=True)

    for first_key, first_level_data in quant_dict.items():
        # If dictionary has a second level, means csv files must be organized in subfolders
        if isinstance(first_level_data, dict):
            pathlib.Path(f"{output_folder}/{first_key}").mkdir(parents=True, exist_ok=True)
            for second_key, second_level_data in first_level_data.items():
                write_lines_to_csv_file(second_level_data, f"{output_folder}/{first_key}/{second_key}.csv", sort_order)
        # If dictionary doesn't have a second level, means csv files must be in a single folder
        else:
            write_lines_to_csv_file(first_level_data, f"{output_folder}/{first_key}.csv", sort_order)


class Command(BaseCommand):
    quant_headers = []
    help = "To recursively read all quant dump csv files in a folder then reorganize them as requested"

    def add_arguments(self, parser):
        parser.add_argument("command", type=str, help="Command to run")
        parser.add_argument("input_folder", type=str, help="Path of the folder containing CSV files")
        parser.add_argument("output_folder", type=str, help="Root output folder")
        parser.add_argument("sort_order", type=str, nargs="?", help="Date sort order (asc or desc)")

    def handle(self, *args, **options):
        if options["command"] == "by_date_then_type":
            quant_dict = aggregate_csv_quant_files(options["input_folder"], Columns.DATE, Columns.TYPE)
        elif options["command"] == "by_type_then_date":
            quant_dict = aggregate_csv_quant_files(options["input_folder"], Columns.TYPE, Columns.DATE)
        elif options["command"] == "one_csv_per_date":
            quant_dict = aggregate_csv_quant_files(options["input_folder"], Columns.DATE)
        elif options["command"] == "one_csv_per_type":
            quant_dict = aggregate_csv_quant_files(options["input_folder"], Columns.TYPE)
        else:
            print("Unknown command")
            return

        # Export all quant data to csv files, organized according to the dictionary structure
        process_quant_for_output(quant_dict, options["output_folder"], options["sort_order"])
