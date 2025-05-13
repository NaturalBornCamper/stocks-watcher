from datetime import datetime, date

from django.db.models import Max, Count, Sum, F
from django.http import HttpResponse
from pyrotools.log import Log

from apps.quant.models import SARating, CompiledSAScore, SAStock, CompiledSAScoreDecayed

MAX_QUANT_TYPES_PER_RUN = 5
DECAY_FACTOR = 0.05


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


def compile_quant(request):
    Log.d("TODO replace all prints with logging")
    max_quant_types = int(request.GET.get("limit", MAX_QUANT_TYPES_PER_RUN))

    # Get the date of the latest quant data from Seeking Alpha dumps
    latest_quant_dump_date = SARating.objects.aggregate(latest_date=Max('date'))['latest_date']
    print(f"Latest quant dump: {latest_quant_dump_date}")
    if not latest_quant_dump_date:
        return HttpResponse("No quant data found")

    # Get quant types that have not been compiled yet (compilation date smaller than quant date)
    types_to_update = []
    for quant_type in SARating.TYPES.keys():
        # Exclude this quant type if it already has a compilation date greater than the latest date
        if CompiledSAScore.objects.filter(latest_quant_date__gte=latest_quant_dump_date, type=quant_type).exists():
            print(f"Quant type already compiled: {quant_type}")
            continue

        # Don't fetch more types to compile than the max requested
        if len(types_to_update) >= max_quant_types:
            break
        types_to_update.append(quant_type)

    # For each quant type, get ALL the quant rows and compile the score
    for current_type in types_to_update:
        compiled_type = (
            SARating.objects
            .filter(type=current_type)
            .values("sa_stock", "type")  # Grouping fields
            .annotate(count=Count("pk"), score=Sum(101 - F('rank')))
        )

        # Convert the query results to a list of CompiledSAScore objects for model insert
        compiled_type_instances = []
        for entry in compiled_type:
            compiled_type_instances.append(CompiledSAScore(
                sa_stock=SAStock.objects.get(pk=entry["sa_stock"]),
                type=entry["type"],
                score=entry["score"],
                count=entry["count"],
                latest_quant_date=latest_quant_dump_date
            ))

        # Update the Compiled Quant table (New stock symbols will be added, existing symbols will be updated)
        CompiledSAScore.objects.bulk_create(
            compiled_type_instances,
            update_conflicts=True,
            update_fields=["count", "score", "latest_quant_date"],
            unique_fields=["sa_stock", "type"],  # Fields to match existing rows that need to updating
        )
        print(f"Compiled type: {SARating.TYPES[current_type]} ({compiled_type.count()} stock symbols)")

    return HttpResponse(f"Compiled {len(types_to_update)} quant types")


def compile_quant_decay(request):
    max_quant_types = int(request.GET.get("limit", MAX_QUANT_TYPES_PER_RUN))
    decay_months = int(request.GET.get("decay_months", CompiledSAScoreDecayed.DECAY_MONTHS))
    print(f"Max decay distance: {decay_months}")

    # Builds the decay factor list of length (max_decay_distance + 1). For example:
    # max_decay_distance 3 => [1.0, 0.75, 0.5, 0.25]
    # max_decay_distance 1 => [1.0, 0.5]
    decay_factors = [1.0 - (i / (decay_months)) for i in range(decay_months)]
    print(f"Decay factors: {decay_factors}")

    latest_quant_dump_date = SARating.objects.aggregate(latest_date=Max('date'))['latest_date']
    if not latest_quant_dump_date:
        return HttpResponse("No quant data found")
    print(f"Latest quant dump: {latest_quant_dump_date}")

    earliest_quant_date = rewind_months(latest_quant_dump_date, decay_months - 1)

    # Build array of quant types to compile
    types_to_update = []
    for quant_type in SARating.TYPES.keys():
        if CompiledSAScoreDecayed.objects.filter(latest_quant_date__gte=latest_quant_dump_date, type=quant_type).exists():
            print(f"Quant type already compiled: {quant_type}")
            continue
        if len(types_to_update) >= max_quant_types:
            break
        types_to_update.append(quant_type)

    compiled_quants_with_decay = {}
    for current_type in types_to_update:
        print(f"Processing quant type: {SARating.TYPES[current_type]}")

        # Clear old values
        CompiledSAScoreDecayed.objects.filter(type=current_type).delete()

        # Get all quant data with given type and date > maximum months back
        for quant in (SARating.objects.filter(type=current_type, date__gte=earliest_quant_date).order_by("date")):
            decay_factor = decay_factors[get_distance_in_months(quant.date, latest_quant_dump_date)]

            # Add sa_stock to the dictionary if it doesn't exist yet
            if quant.sa_stock not in compiled_quants_with_decay:
                compiled_quants_with_decay[quant.sa_stock] = CompiledSAScoreDecayed(
                    sa_stock=quant.sa_stock,
                    type=current_type,
                    score=0,
                    count=0,
                    latest_quant_date=latest_quant_dump_date
                )

            # Calculate the new decayed score and append values for debug
            compiled_quants_with_decay[quant.sa_stock].count += 1
            compiled_quants_with_decay[quant.sa_stock].score += int((101 - quant.rank) * decay_factor)

    if compiled_quants_with_decay:
        CompiledSAScoreDecayed.objects.bulk_create(compiled_quants_with_decay.values())

    return HttpResponse(f"Compiled {len(types_to_update)} quant types")
