import csv
import pathlib
from datetime import datetime

from django.core.management.base import BaseCommand

from utils.quant import find_matching_value, Columns, COLUMN_NAME_VARIANTS


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


# Recursively reads all quant dump csv files in a folder and aggregates them into a single dictionary
def aggregate_csv_quant_files(input_folder: str, first_key: str, second_key: str = None) -> dict:
    csv_filepaths = pathlib.Path(input_folder).rglob("*.csv")
    quant_dict = {}

    for csv_filepath in csv_filepaths:
        with csv_filepath.open("r") as f:
            dict_reader = csv.DictReader(f)

            for row in dict_reader:
                # Convert old column names to new column names
                new_row = {}
                for col_name, possible_names in COLUMN_NAME_VARIANTS.items():
                    new_row[col_name] = find_matching_value(row, possible_names)

                first_key_value = new_row.get(first_key, None)
                if not first_key_value:
                    print(f"Missing key: {first_key} in row: {new_row}, skipping")
                    continue

                if first_key_value not in quant_dict:
                    quant_dict[first_key_value] = {} if second_key is not None else []
                if second_key is not None:
                    second_key_value = new_row.get(second_key, None)
                    if not second_key_value:
                        print(f"Missing key: {second_key} in row: {new_row}, skipping")
                        continue

                    if second_key_value not in quant_dict[first_key_value]:
                        quant_dict[first_key_value][second_key_value] = []
                    quant_dict[first_key_value][second_key_value].append(new_row)
                else:
                    quant_dict[first_key_value].append(new_row)

    return quant_dict


# Writes a list of lines to a csv file, sorting them if necessary
def write_lines_to_csv_file(lines: list[dict[str, str]], output_file: str, sort_order: str) -> None:
    # Sort quant list by their date (asc or desc), then type, then rank
    # date sorting has no effect on multi-levels export (since a folder per date, or a file per date)
    if sort_order:
        lines.sort(key=lambda x: (
            datetime.strptime(x[Columns.DATE], "%Y-%m-%d").timestamp() * (-1 if sort_order == "desc" else 1),
            x[Columns.TYPE],
            int(x[Columns.RANK])
        ))

    with open(output_file, "w", newline='') as f:
        dict_writer = csv.DictWriter(f, fieldnames=COLUMN_NAME_VARIANTS.keys(), quoting=csv.QUOTE_ALL, lineterminator='\n')
        dict_writer.writeheader()
        for line in lines:
            dict_writer.writerow(line)


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