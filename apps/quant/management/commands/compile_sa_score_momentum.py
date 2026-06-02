from django.core.management.base import BaseCommand
from django.db.models import Max

from apps.quant.models import CompiledSAScoreMomentum, SARating
from apps.quant.scoring import (
    MAX_SA_RATING_TYPES_PER_RUN,
    get_distance_in_months,
    get_types_pending_compilation,
    rewind_months,
)


# Cronjob command: compile the "rising stars" momentum SA score for each stock.
# Combines current rank quality (base) with rank-change velocity (momentum):
# final = base + --momentum-weight * momentum, over a --window-months window.
# See quant_simulations/README.md for the algorithm and worked examples.
# Only rating types not already compiled for the latest dump are processed,
# capped at --limit per run.
# Usage
#  python manage.py compile_sa_score_momentum
#  python manage.py compile_sa_score_momentum --limit 5
#  python manage.py compile_sa_score_momentum --window-months 5 --momentum-weight 2.0


class Command(BaseCommand):
    help = "Compile the momentum / rising-stars Seeking Alpha score for each stock."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=MAX_SA_RATING_TYPES_PER_RUN,
            help="Max number of SA rating types to compile in this run.",
        )
        parser.add_argument(
            "--window-months",
            type=int,
            default=CompiledSAScoreMomentum.WINDOW_MONTHS,
            help="How many recent months the base and momentum are measured over.",
        )
        parser.add_argument(
            "--momentum-weight",
            type=float,
            default=CompiledSAScoreMomentum.MOMENTUM_WEIGHT,
            help="How strongly rank-change velocity counts relative to the base score.",
        )

    def handle(self, *args, **options):
        max_quant_types = options["limit"]
        window_months = options["window_months"]
        momentum_weight = options["momentum_weight"]
        self.stdout.write(f"Window months: {window_months}, momentum weight: {momentum_weight}")

        # Position decay weights for the base score -- recent months count more.
        # window=5 => [1.0, 0.8, 0.6, 0.4, 0.2]
        pos_decay = [(window_months - i) / window_months for i in range(window_months)]
        pos_decay_sum = sum(pos_decay)

        # Slope decay weights for momentum -- recent slope counts more.
        # window=5 => [1.0, 0.75, 0.5, 0.25]
        slope_decay = [(window_months - 1 - i) / (window_months - 1) for i in range(window_months - 1)]
        slope_decay_sum = sum(slope_decay)
        self.stdout.write(f"Position decay: {pos_decay}")
        self.stdout.write(f"Slope decay:    {slope_decay}")

        latest_quant_dump_date = SARating.objects.aggregate(latest_date=Max("date"))["latest_date"]
        self.stdout.write(f"Latest Seeking Alpha ratings date: {latest_quant_dump_date}")
        if not latest_quant_dump_date:
            self.stdout.write("No ratings data found")
            return

        earliest_quant_date = rewind_months(latest_quant_dump_date, window_months - 1)

        types_to_update = get_types_pending_compilation(
            CompiledSAScoreMomentum, latest_quant_dump_date, max_quant_types, write=self.stdout.write
        )

        for current_type in types_to_update:
            self.stdout.write(f"Processing ratings of type: {SARating.TYPES[current_type]}")

            # Clear old values.
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
            self.stdout.write(f"Compiled type: {SARating.TYPES[current_type]} ({len(instances)} stock symbols)")

        self.stdout.write(self.style.SUCCESS(f"Compiled {len(types_to_update)} Seeking Alpha momentum score types"))