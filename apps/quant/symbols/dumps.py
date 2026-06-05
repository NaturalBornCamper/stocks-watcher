import csv
import pathlib
import re

from utils.quant import Columns, COLUMN_NAME_VARIANTS

SA_DUMPS_FOLDER = "data_dumps/seeking_alpha"

# Dated monthly dumps look like 2026-06-01.csv; the raw per-category exports
# (top_growth.csv etc.) and helper files do not match this pattern
DATED_DUMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}\.csv$")


def find_dump_files(folder=SA_DUMPS_FOLDER):
    """All dump CSVs in the folder (dated monthlies + per-category exports),
    oldest first, skipping "_"-prefixed helper/cache files."""
    files = sorted(pathlib.Path(folder).glob("*.csv"))
    return [file for file in files if not file.name.startswith("_")]


def find_dated_dump_files(folder=SA_DUMPS_FOLDER):
    """Only the dated monthly dumps (YYYY-MM-DD.csv), oldest first, so the last
    entry is always the newest month."""
    return [file for file in find_dump_files(folder) if DATED_DUMP_PATTERN.match(file.name)]


def read_dump(csv_file):
    """Load one dump CSV. Returns (fieldnames, rows) where each row is a dict.

    Always reads UTF-8: the dumps hold accented company names ("América Móvil")
    and the Windows default encoding (cp1252) would mangle them."""
    with open(csv_file, "r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        return reader.fieldnames, list(reader)


def write_dump(csv_file, fieldnames, rows):
    """Write one dump CSV back in the same style as the originals: UTF-8, every
    field quoted, Unix line endings.

    The "\\n" line terminator matters -- it matches what sa_ratings_manipulations
    generates and what git stores, so rewriting a file does not churn every line."""
    with open(csv_file, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def find_column(fieldnames, column):
    """Find which header this dump file uses for one of our standard columns
    (e.g. "Seeking Alpha Symbol" in monthly dumps vs plain "Symbol" in the raw
    per-category exports)."""
    return next((name for name in COLUMN_NAME_VARIANTS[column] if name in fieldnames), None)
