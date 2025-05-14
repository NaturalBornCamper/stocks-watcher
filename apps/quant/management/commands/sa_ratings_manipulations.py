import csv
import pathlib
from collections import defaultdict
from datetime import datetime

from django.core.management.base import BaseCommand

from utils.quant import find_matching_value, Columns, COLUMN_NAME_VARIANTS


# SEEKING ALPHA RATING DUMPS MANIPULATIONS
# Executes these 3 steps:
#  1-Recursively reads all SA rating CSV dump files from an input folder
#  2-Aggregates them into a single dictionary
#  3-Splits the generated rating data dictionary into the different csv files, as requested
# Example usage:
# python manage.py sa_ratings_manipulations <function> /path/to/your/csv_dump_folder /path/to/your/output_folder <asc|desc>
# python manage.py sa_ratings_manipulations by_date_then_type "SA Rating Dumps/" "organized_ratings"
# python manage.py sa_ratings_manipulations by_type_then_date "SA Rating Dumps/" "organized_ratings"
# python manage.py sa_ratings_manipulations one_csv_per_date "SA Rating Dumps/" "organized_ratings" asc
# python manage.py sa_ratings_manipulations one_csv_per_type "SA Rating Dumps/" "organized_ratings" desc
# I usually use this one:
#  python manage.py sa_ratings_manipulations one_csv_per_date "data_dumps/seeking_alpha/" "data_dumps/seeking_alpha/"

class SeekingAlphaRatingsAggregator:
    def __init__(self, group_field: str, subgroup_field: str = None):
        self.group_field = group_field
        self.subgroup_field = subgroup_field
        self.data = {}

    # Read all SA rating CSV dump files recursively from the input folder and organize them all in a dictionary to prevent duplicates
    def aggregate_files(self, input_folder: str) -> None:
        # Build the required columns list and the result dictionary, depending on the number of grouping levels
        if self.subgroup_field:
            required_columns = [self.group_field, self.subgroup_field, Columns.DATE, Columns.TYPE, Columns.RANK]
            # Three-level structure: result["main_group"]["sub_group"]["third_key"] = {"csv_column1": "value1", ...}
            self.data = defaultdict(lambda: defaultdict(dict))
        else:
            required_columns = [self.group_field, Columns.DATE, Columns.TYPE, Columns.RANK]
            # Two-level structure: result["main_group"]["third_key"] = {"csv_column1": "value1", ...}
            self.data = defaultdict(dict)

        for csv_filepath in pathlib.Path(input_folder).rglob("*.csv"):
            with csv_filepath.open("r") as f:
                dict_reader = csv.DictReader(f)

                for row in dict_reader:
                    # If a required column is missing, skip the row
                    if missing_columns := [col for col in required_columns if col not in row]:
                        print(f"Missing columns: {missing_columns}, skipping row")
                        continue

                    # Convert old column names to new column names
                    new_row = {}
                    for col_name, possible_names in COLUMN_NAME_VARIANTS.items():
                        new_row[col_name] = find_matching_value(row, possible_names)

                    # Generate the keys for the result dictionary
                    main_group_value = new_row.get(self.group_field, None)
                    sub_group_value = new_row.get(self.subgroup_field, None)
                    row_key = new_row[Columns.DATE] + "_" + new_row[Columns.TYPE] + "_" + new_row[Columns.RANK]

                    # Add the new row to the result dictionary
                    if self.subgroup_field:
                        self.data[main_group_value][sub_group_value][row_key] = new_row
                    else:
                        self.data[main_group_value][row_key] = new_row

    def write_output(self, output_folder: str, sort_order: str) -> None:
        pathlib.Path(output_folder).mkdir(parents=True, exist_ok=True)

        for first_key, first_level_data in self.data.items():
            if self.subgroup_field:
                pathlib.Path(f"{output_folder}/{first_key}").mkdir(parents=True, exist_ok=True)
                for second_key, second_level_data in first_level_data.items():
                    self._write_csv(
                        second_level_data,
                        f"{output_folder}/{first_key}/{second_key}.csv",
                        sort_order
                    )
            else:
                # print(first_level_data)
                self._write_csv(
                    first_level_data,
                    f"{output_folder}/{first_key}.csv",
                    sort_order
                )

    @staticmethod
    def _write_csv(data: dict, filepath: str, sort_order: str) -> None:
        # def write_lines_to_csv_file(lines: list[dict[str, str]], output_file: str, sort_order: str) -> None:
        lines = [row_data for row_data in data.values()]
        output_file = filepath

        # Sort ratings list by their date (asc or desc), then type, then rank
        # date sorting has no effect on multi-levels export (since a folder per date, or a file per date)
        if sort_order:
            lines.sort(key=lambda x: (
                datetime.strptime(x[Columns.DATE], "%Y-%m-%d").timestamp() * (-1 if sort_order == "desc" else 1),
                x[Columns.TYPE],
                int(x[Columns.RANK])
            ))

        with open(output_file, "w", newline='') as f:
            dict_writer = csv.DictWriter(
                f, fieldnames=COLUMN_NAME_VARIANTS.keys(), quoting=csv.QUOTE_ALL, lineterminator='\n'
            )
            dict_writer.writeheader()
            for line in lines:
                dict_writer.writerow(line)


class Command(BaseCommand):
    help = "To recursively read all Seeking Alpha rating csv dump files in a folder then reorganize them as requested"

    def add_arguments(self, parser):
        parser.add_argument("command", type=str, help="Command to run")
        parser.add_argument("input_folder", type=str, help="Path of the folder containing CSV files")
        parser.add_argument("output_folder", type=str, help="Root output folder")
        parser.add_argument("sort_order", type=str, nargs="?", help="Date sort order (asc or desc)")

    def handle(self, *args, **options):
        if options["command"] == "by_date_then_type":
            aggregator = SeekingAlphaRatingsAggregator(group_field=Columns.DATE, subgroup_field=Columns.TYPE)
        elif options["command"] == "by_type_then_date":
            aggregator = SeekingAlphaRatingsAggregator(group_field=Columns.TYPE, subgroup_field=Columns.DATE)
        elif options["command"] == "one_csv_per_date":
            aggregator = SeekingAlphaRatingsAggregator(group_field=Columns.DATE)
        elif options["command"] == "one_csv_per_type":
            aggregator = SeekingAlphaRatingsAggregator(group_field=Columns.TYPE)
        else:
            print("Unknown command")
            return

        # Splits the generated rating data dictionary into the different csv files
        aggregator.aggregate_files(options["input_folder"])

        # Export all rating data to csv files, organized according to the dictionary structure
        aggregator.write_output(options["output_folder"], options["sort_order"])
