from datetime import datetime, date

from django.db.models import Max, Count, Sum, F
from django.http import HttpResponse
from pyrotools.log import Log

from apps.quant.models import SARating, CompiledSAScore, SAStock, CompiledSADeltaScore, CompiledSAScoreDecayed, \
    CompiledSADeltaScoreDecayed, DeltaScoreBase

MAX_SA_RATING_TYPES_PER_RUN = 5
DECAY_FACTOR = 0.05
DELTA_SLOPE_COEFFICIENT = 1.0
DELTA_RANK_COEFFICIENT = 1.0
OUT_OF_RANGE_RANK = 200


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


def compile_sa_score(request):
    Log.d("TODO replace all prints with logging")
    max_quant_types = int(request.GET.get("limit", MAX_SA_RATING_TYPES_PER_RUN))

    # Get the date of the latest Seeking Alpha ratings data dumps
    latest_quant_dump_date = SARating.objects.aggregate(latest_date=Max('date'))['latest_date']
    print(f"Latest Seeking Alpha ratings date: {latest_quant_dump_date}")
    if not latest_quant_dump_date:
        return HttpResponse("No ratings data found")

    # Get scores types that have not been compiled yet (compilation date earlier than latest ratings date)
    types_to_update = []
    for quant_type in SARating.TYPES.keys():
        # Exclude this score type if it already has a compilation date later than the latest sa ratings date
        if CompiledSAScore.objects.filter(latest_sa_ratings_date__gte=latest_quant_dump_date, type=quant_type).exists():
            print(f"Ratings type already compiled: {quant_type}")
            continue

        # Don't fetch more types to compile than the max requested
        if len(types_to_update) >= max_quant_types:
            break
        types_to_update.append(quant_type)

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
    decay_factors = [1.0 - (i / (decay_months)) for i in range(decay_months)]
    print(f"Decay factors: {decay_factors}")

    latest_quant_dump_date = SARating.objects.aggregate(latest_date=Max('date'))['latest_date']
    print(f"Latest Seeking Alpha ratings date: {latest_quant_dump_date}")
    if not latest_quant_dump_date:
        return HttpResponse("No ratings data found")

    earliest_quant_date = rewind_months(latest_quant_dump_date, decay_months - 1)

    # Build array of quant types to compile
    types_to_update = []
    for quant_type in SARating.TYPES.keys():
        if CompiledSAScoreDecayed.objects.filter(latest_sa_ratings_date__gte=latest_quant_dump_date, type=quant_type).exists():
            print(f"Score type already compiled: {quant_type}")
            continue
        if len(types_to_update) >= max_quant_types:
            break
        types_to_update.append(quant_type)

    compiled_quants_with_decay = {}
    for current_type in types_to_update:
        print(f"Processing ratings of type: {SARating.TYPES[current_type]}")

        # Clear old values
        CompiledSAScoreDecayed.objects.filter(type=current_type).delete()

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

            # Calculate the new decayed score and append values for debug
            compiled_quants_with_decay[rating.sa_stock].count += 1
            compiled_quants_with_decay[rating.sa_stock].score += int((101 - rating.rank) * decay_factor)

    if compiled_quants_with_decay:
        CompiledSAScoreDecayed.objects.bulk_create(compiled_quants_with_decay.values())

    return HttpResponse(f"Compiled {len(types_to_update)} Seeking Alpha score types")


def calculate_consecutive_differences(values: list, use_decay: bool = False) -> float:
    if len(values) < 2:
        return 0

    total = 0
    num_differences = len(values) - 1

    # Generate decay factors if requested
    if use_decay:
        decay_factors = [1.0 - (i / num_differences) for i in range(num_differences)]
    else:
        decay_factors = [1.0] * num_differences
    # print(f"Decay factors: {decay_factors}")

    for i in range(num_differences):
        difference = values[i + 1] - values[i]
        weighted_difference = difference * decay_factors[i]
        total += weighted_difference

    # return total / num_differences
    return total


def compile_sa_delta_score(request):
    max_quant_types = int(request.GET.get("limit", MAX_SA_RATING_TYPES_PER_RUN))
    out_of_range_rank = int(request.GET.get("out_of_range_rank", OUT_OF_RANGE_RANK))
    use_decay = request.GET.get("use_decay", "").lower() not in ("", "false", "0", "no", "off")
    print(f"Use decay: {use_decay}")
    sample_month_count = int(request.GET.get("decay_months", DeltaScoreBase.SAMPLE_MONTH_COUNT))
    print(f"Max months history: {sample_month_count}")

    DeltaModelToUse = CompiledSADeltaScore if not use_decay else CompiledSADeltaScoreDecayed


    # Builds the decay factor list of length (max_decay_distance + 1). For example:
    # sample_month_count 3 => [1.0, 0.75, 0.5, 0.25]
    # sample_month_count 1 => [1.0, 0.5]
    decay_factors = [1.0 - (i / sample_month_count) for i in range(sample_month_count)]
    print(f"Decay factors: {decay_factors}")

    latest_quant_dump_date = SARating.objects.aggregate(latest_date=Max('date'))['latest_date']
    print(f"Latest Seeking Alpha ratings date: {latest_quant_dump_date}")
    if not latest_quant_dump_date:
        return HttpResponse("No ratings data found")

    earliest_quant_date = rewind_months(latest_quant_dump_date, sample_month_count - 1)

    # Build array of quant types to compile
    types_to_update = []
    for quant_type in SARating.TYPES.keys():
        if DeltaModelToUse.objects.filter(latest_sa_ratings_date__gte=latest_quant_dump_date, type=quant_type).exists():
            print(f"Score type already compiled: {quant_type}")
            continue
        if len(types_to_update) >= max_quant_types:
            break
        types_to_update.append(quant_type)

    for current_type in types_to_update:
        print(f"Processing ratings of type: {SARating.TYPES[current_type]}")

        # Clear old values
        DeltaModelToUse.objects.filter(type=current_type).delete()

        compiled_delta_scores = {}
        ranks_list = {}

        # Get all SA ratings data with given type & date > maximum months back
        for rating in (SARating.objects.filter(type=current_type, date__gte=earliest_quant_date).order_by("date")):
            distance_in_months = get_distance_in_months(rating.date, latest_quant_dump_date)
            decay_factor = decay_factors[distance_in_months] if use_decay else 1

            # Add sa_stock to the dictionary if it doesn't exist yet
            if rating.sa_stock not in compiled_delta_scores:
                compiled_delta_scores[rating.sa_stock] = CompiledSADeltaScoreDecayed(
                    sa_stock=rating.sa_stock,
                    type=current_type,
                    combined_score=0,
                    slope_score=0,
                    rank_score=0,
                    count=0,
                    latest_sa_ratings_date=latest_quant_dump_date
                )
                ranks_list[rating.sa_stock] = [out_of_range_rank] * 5

            # print(rating.sa_stock, distance_in_months, rating.rank)
            ranks_list[rating.sa_stock][distance_in_months] = rating.rank

            # Calculate the new decayed scores
            compiled_delta_scores[rating.sa_stock].count += 1
            compiled_delta_scores[rating.sa_stock].rank_score += int((101 - rating.rank) * decay_factor)

        for sa_stock, ranks in ranks_list.items():
            slope_score = calculate_consecutive_differences(ranks, use_decay=use_decay)
            compiled_delta_scores[sa_stock].slope_score = slope_score
            compiled_delta_scores[sa_stock].combined_score = (
                    DELTA_SLOPE_COEFFICIENT * slope_score +
                    DELTA_RANK_COEFFICIENT * compiled_delta_scores[sa_stock].rank_score
            )
            compiled_delta_scores[sa_stock].ranks = ranks
            # print(f"{ranks} = {slope_score}")

        # for sa_Stock, compiled_quant_with_decay in compiled_delta_scores.items():
        #     print(f"combined_score {compiled_quant_with_decay.combined_score}, slope_score {compiled_quant_with_decay.slope_score}, rank_score: {compiled_quant_with_decay.rank_score}, count: {compiled_quant_with_decay.count}")

        if compiled_delta_scores:
            DeltaModelToUse.objects.bulk_create(compiled_delta_scores.values())

    return HttpResponse(f"Compiled {len(types_to_update)} Seeking Alpha delta score types")
