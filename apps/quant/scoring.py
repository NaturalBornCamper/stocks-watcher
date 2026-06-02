"""
Shared helpers for compiling per-stock Seeking Alpha scores.

These used to live in apps/quant/views/cron.py, but they are plain
date / query helpers with nothing view-specific about them. They are
used by the compile_sa_score* management commands and by the
backtest_scores research command.
"""
from datetime import date, datetime

from apps.quant.models import SARating

# How many SA rating types a single compile run handles at most, so one run
# does not process them all at once. Used as the default for the --limit flag.
MAX_SA_RATING_TYPES_PER_RUN = 5


# Returns the amount of months between two dates (dates must be the first of the month)
def get_distance_in_months(earliest_date: datetime.date, latest_date: datetime.date) -> int:
    if not isinstance(earliest_date, date) or not isinstance(latest_date, date):
        raise TypeError(f"Dates must be datetime.date objects. Types: {type(earliest_date)}, {type(latest_date)}")

    if earliest_date.day != 1 or latest_date.day != 1:
        raise ValueError(f"Dates must be the first of the month. date1: {earliest_date}, date2: {latest_date}")

    months = (latest_date.year - earliest_date.year) * 12 + (latest_date.month - earliest_date.month)
    return months


# Goes back <months_to_rewind> in the past from a given date and returns the first day of that month
def rewind_months(from_date: date, months_to_rewind) -> date:
    adjusted_year, adjusted_month = from_date.year, from_date.month - months_to_rewind
    if adjusted_month < 1:
        adjusted_year -= 1
        adjusted_month += 12

    return date(adjusted_year, adjusted_month, 1)


# Returns the SARating type keys that have no compilation row yet for the given dump date.
# Caps the result at max_types so a single run doesn't process them all at once.
# `write` is where progress lines go (a command passes self.stdout.write so the
# cron runner captures them; defaults to print for plain calls like the backtest).
def get_types_pending_compilation(model_cls, latest_dump_date, max_types, write=print):
    pending = []
    for quant_type in SARating.TYPES.keys():
        if model_cls.objects.filter(latest_sa_ratings_date__gte=latest_dump_date, type=quant_type).exists():
            write(f"Ratings type already compiled: {quant_type}")
            continue
        if len(pending) >= max_types:
            break
        pending.append(quant_type)
    return pending