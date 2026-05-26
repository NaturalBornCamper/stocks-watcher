from datetime import datetime, date

from django.db.models import Max, Count, Sum, F
from django.http import HttpResponse
from pyrotools.log import Log

from apps.quant.models import (
    SARating,
    CompiledSAScore,
    SAStock,
    CompiledSAScoreDecayed,
    CompiledSAScoreMomentum,
)

MAX_SA_RATING_TYPES_PER_RUN = 5
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


# Returns the SARating type keys that have no compilation row yet for the given dump date.
# Caps the result at max_types so a single cron invocation doesn't process them all at once.
def get_types_pending_compilation(model_cls, latest_dump_date, max_types):
    pending = []
    for quant_type in SARating.TYPES.keys():
        if model_cls.objects.filter(latest_sa_ratings_date__gte=latest_dump_date, type=quant_type).exists():
            print(f"Ratings type already compiled: {quant_type}")
            continue
        if len(pending) >= max_types:
            break
        pending.append(quant_type)
    return pending


def compile_sa_score(request):
    Log.d("TODO replace all prints with logging")
    max_quant_types = int(request.GET.get("limit", MAX_SA_RATING_TYPES_PER_RUN))

    # Get the date of the latest Seeking Alpha ratings data dumps
    latest_quant_dump_date = SARating.objects.aggregate(latest_date=Max('date'))['latest_date']
    print(f"Latest Seeking Alpha ratings date: {latest_quant_dump_date}")
    if not latest_quant_dump_date:
        return HttpResponse("No ratings data found")

    types_to_update = get_types_pending_compilation(CompiledSAScore, latest_quant_dump_date, max_quant_types)

    # For each SA score type, get ALL the rating rows and compile the score
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
                latest_sa_ratings_date=latest_quant_dump_date
            ))

        # Update the Compiled Quant table (New stock symbols will be added, existing symbols will be updated)
        CompiledSAScore.objects.bulk_create(
            compiled_type_instances,
            update_conflicts=True,
            update_fields=["count", "score", "latest_sa_ratings_date"],
            unique_fields=["sa_stock", "type"],  # Fields to match existing rows that need to updating
        )
        print(f"Compiled type: {SARating.TYPES[current_type]} ({compiled_type.count()} stock symbols)")

    return HttpResponse(f"Compiled {len(types_to_update)} Seeking Alpha score types")


def compile_sa_score_decayed(request):
    max_quant_types = int(request.GET.get("limit", MAX_SA_RATING_TYPES_PER_RUN))
    decay_months = int(request.GET.get("decay_months", CompiledSAScoreDecayed.DECAY_MONTHS))
    print(f"Max decay distance: {decay_months}")

    # Builds the decay factor list of length (max_decay_distance + 1). For example:
    # max_decay_distance 3 => [1.0, 0.75, 0.5, 0.25]
    # max_decay_distance 1 => [1.0, 0.5]
    decay_factors = [1.0 - (i / decay_months) for i in range(decay_months)]
    print(f"Decay factors: {decay_factors}")

    latest_quant_dump_date = SARating.objects.aggregate(latest_date=Max('date'))['latest_date']
    print(f"Latest Seeking Alpha ratings date: {latest_quant_dump_date}")
    if not latest_quant_dump_date:
        return HttpResponse("No ratings data found")

    earliest_quant_date = rewind_months(latest_quant_dump_date, decay_months - 1)

    types_to_update = get_types_pending_compilation(CompiledSAScoreDecayed, latest_quant_dump_date, max_quant_types)

    for current_type in types_to_update:
        print(f"Processing ratings of type: {SARating.TYPES[current_type]}")

        # Clear old values
        CompiledSAScoreDecayed.objects.filter(type=current_type).delete()

        compiled_quants_with_decay = {}
        # Get all SA ratings data with given type & date > maximum months back
        for rating in (SARating.objects.filter(type=current_type, date__gte=earliest_quant_date).order_by("date")):
            decay_factor = decay_factors[get_distance_in_months(rating.date, latest_quant_dump_date)]

            # Add sa_stock to the dictionary if it doesn't exist yet
            if rating.sa_stock not in compiled_quants_with_decay:
                compiled_quants_with_decay[rating.sa_stock] = CompiledSAScoreDecayed(
                    sa_stock=rating.sa_stock,
                    type=current_type,
                    score=0,
                    count=0,
                    latest_sa_ratings_date=latest_quant_dump_date
                )

            # Calculate the new decayed score and append values
            compiled_quants_with_decay[rating.sa_stock].count += 1
            compiled_quants_with_decay[rating.sa_stock].score += int((101 - rating.rank) * decay_factor)

        if compiled_quants_with_decay:
            CompiledSAScoreDecayed.objects.bulk_create(compiled_quants_with_decay.values())

    return HttpResponse(f"Compiled {len(types_to_update)} Seeking Alpha score types")


# Compiles the "rising stars" score combining current rank quality (base) with rank-change
# velocity (momentum). See README.md for the algorithm and worked examples.
def compile_sa_score_momentum(request):
    max_quant_types = int(request.GET.get("limit", MAX_SA_RATING_TYPES_PER_RUN))
    window_months = int(request.GET.get("window_months", CompiledSAScoreMomentum.WINDOW_MONTHS))
    momentum_weight = float(request.GET.get("momentum_weight", CompiledSAScoreMomentum.MOMENTUM_WEIGHT))
    print(f"Window months: {window_months}, momentum weight: {momentum_weight}")

    # Position decay weights for the base score -- recent months count more.
    # window=5 => [1.0, 0.8, 0.6, 0.4, 0.2]
    pos_decay = [(window_months - i) / window_months for i in range(window_months)]
    pos_decay_sum = sum(pos_decay)

    # Slope decay weights for momentum -- recent slope counts more.
    # window=5 => [1.0, 0.75, 0.5, 0.25]
    slope_decay = [(window_months - 1 - i) / (window_months - 1) for i in range(window_months - 1)]
    slope_decay_sum = sum(slope_decay)
    print(f"Position decay: {pos_decay}")
    print(f"Slope decay:    {slope_decay}")

    latest_quant_dump_date = SARating.objects.aggregate(latest_date=Max('date'))['latest_date']
    print(f"Latest Seeking Alpha ratings date: {latest_quant_dump_date}")
    if not latest_quant_dump_date:
        return HttpResponse("No ratings data found")

    earliest_quant_date = rewind_months(latest_quant_dump_date, window_months - 1)

    types_to_update = get_types_pending_compilation(CompiledSAScoreMomentum, latest_quant_dump_date, max_quant_types)

    for current_type in types_to_update:
        print(f"Processing ratings of type: {SARating.TYPES[current_type]}")

        # Clear old values
        CompiledSAScoreMomentum.objects.filter(type=current_type).delete()

        # Per-stock buckets: an array of length window_months, indexed by months-back-from-latest.
        # index 0 = newest month, index window_months-1 = oldest. Missing months stay at 0
        # (which is exactly what "not in the top 100" should produce).
        stock_values = {}
        stock_counts = {}
        for rating in SARating.objects.filter(type=current_type, date__gte=earliest_quant_date):
            distance = get_distance_in_months(rating.date, latest_quant_dump_date)
            value = max(0, 101 - rating.rank)

            if rating.sa_stock_id not in stock_values:
                stock_values[rating.sa_stock_id] = [0] * window_months
                stock_counts[rating.sa_stock_id] = 0

            stock_values[rating.sa_stock_id][distance] = value
            stock_counts[rating.sa_stock_id] += 1

        instances = []
        for sa_stock_id, values in stock_values.items():
            base = sum(v * w for v, w in zip(values, pos_decay)) / pos_decay_sum
            slopes = [values[i] - values[i + 1] for i in range(window_months - 1)]
            momentum = sum(s * w for s, w in zip(slopes, slope_decay)) / slope_decay_sum
            final = base + momentum_weight * momentum

            instances.append(CompiledSAScoreMomentum(
                sa_stock_id=sa_stock_id,
                type=current_type,
                score=int(round(final)),
                count=stock_counts[sa_stock_id],
                latest_sa_ratings_date=latest_quant_dump_date,
            ))

        if instances:
            CompiledSAScoreMomentum.objects.bulk_create(instances)
        print(f"Compiled type: {SARating.TYPES[current_type]} ({len(instances)} stock symbols)")

    return HttpResponse(f"Compiled {len(types_to_update)} Seeking Alpha momentum score types")