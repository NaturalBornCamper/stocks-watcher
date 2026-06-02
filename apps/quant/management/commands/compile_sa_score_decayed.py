from django.core.management.base import BaseCommand
from django.db.models import Max

from apps.quant.models import CompiledSAScoreDecayed, SARating
from apps.quant.scoring import (
    MAX_SA_RATING_TYPES_PER_RUN,
    get_distance_in_months,
    get_types_pending_compilation,
    rewind_months,
)


# Cronjob command: compile the recency-decayed SA score for each stock.
# Only the last --decay-months months count, each weighted by --decay-base ** i
# (month 0 = newest). For example base 0.5 over 3 months -> [1.0, 0.5, 0.25].
# Only rating types not already compiled for the latest dump are processed,
# capped at --limit per run.
# Usage
#  python manage.py compile_sa_score_decayed
#  python manage.py compile_sa_score_decayed --limit 5
#  python manage.py compile_sa_score_decayed --decay-months 3 --decay-base 0.5


class Command(BaseCommand):
    help = "Compile the recency-decayed Seeking Alpha score for each stock."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=MAX_SA_RATING_TYPES_PER_RUN,
            help="Max number of SA rating types to compile in this run.",
        )
        parser.add_argument(
            "--decay-months",
            type=int,
            default=CompiledSAScoreDecayed.DECAY_MONTHS,
            help="How many recent months to include.",
        )
        parser.add_argument(
            "--decay-base",
            type=float,
            default=CompiledSAScoreDecayed.DECAY_BASE,
            help="Exponential decay base: weight for month i back = base ** i.",
        )

    def handle(self, *args, **options):
        max_quant_types = options["limit"]
        decay_months = options["decay_months"]
        decay_base = options["decay_base"]
        self.stdout.write(f"Max decay distance: {decay_months}, decay base: {decay_base}")

        # Exponential recency curve: weight for month i back = decay_base ** i. For example:
        # decay_base 0.5, decay_months 3 => [1.0, 0.5, 0.25]
        # decay_base 0.5, decay_months 1 => [1.0]
        decay_factors = [decay_base ** i for i in range(decay_months)]
        self.stdout.write(f"Decay factors: {decay_factors}")

        latest_quant_dump_date = SARating.objects.aggregate(latest_date=Max("date"))["latest_date"]
        self.stdout.write(f"Latest Seeking Alpha ratings date: {latest_quant_dump_date}")
        if not latest_quant_dump_date:
            self.stdout.write("No ratings data found")
            return

        earliest_quant_date = rewind_months(latest_quant_dump_date, decay_months - 1)

        types_to_update = get_types_pending_compilation(
            CompiledSAScoreDecayed, latest_quant_dump_date, max_quant_types, write=self.stdout.write
        )

        for current_type in types_to_update:
            self.stdout.write(f"Processing ratings of type: {SARating.TYPES[current_type]}")

            # Clear old values.
            CompiledSAScoreDecayed.objects.filter(type=current_type).delete()

            compiled_quants_with_decay = {}
            # Get all SA ratings data with given type & date >= earliest month in the window.
            for rating in (SARating.objects.filter(type=current_type, date__gte=earliest_quant_date).order_by("date")):
                decay_factor = decay_factors[get_distance_in_months(rating.date, latest_quant_dump_date)]

                # Add sa_stock to the dictionary if it doesn't exist yet.
                if rating.sa_stock not in compiled_quants_with_decay:
                    compiled_quants_with_decay[rating.sa_stock] = CompiledSAScoreDecayed(
                        sa_stock=rating.sa_stock,
                        type=current_type,
                        score=0,
                        count=0,
                        latest_sa_ratings_date=latest_quant_dump_date
                    )

                # Calculate the new decayed score and append values.
                compiled_quants_with_decay[rating.sa_stock].count += 1
                compiled_quants_with_decay[rating.sa_stock].score += int((101 - rating.rank) * decay_factor)

            if compiled_quants_with_decay:
                CompiledSAScoreDecayed.objects.bulk_create(compiled_quants_with_decay.values())

        self.stdout.write(self.style.SUCCESS(f"Compiled {len(types_to_update)} Seeking Alpha score types"))