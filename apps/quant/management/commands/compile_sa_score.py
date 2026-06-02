from django.core.management.base import BaseCommand
from django.db.models import Count, F, Max, Sum

from apps.quant.models import CompiledSAScore, SARating, SAStock
from apps.quant.scoring import MAX_SA_RATING_TYPES_PER_RUN, get_types_pending_compilation


# Cronjob command: compile the all-time cumulative SA score for each stock.
# Score = sum(101 - rank) over every month a stock was ranked, no decay.
# Only rating types not already compiled for the latest dump are processed,
# capped at --limit per run.
# Usage
#  python manage.py compile_sa_score
#  python manage.py compile_sa_score --limit 5      -> compile at most 5 rating types this run


class Command(BaseCommand):
    help = "Compile the all-time cumulative Seeking Alpha score for each stock."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=MAX_SA_RATING_TYPES_PER_RUN,
            help="Max number of SA rating types to compile in this run.",
        )

    def handle(self, *args, **options):
        max_quant_types = options["limit"]

        # Get the date of the latest Seeking Alpha ratings data dump.
        latest_quant_dump_date = SARating.objects.aggregate(latest_date=Max("date"))["latest_date"]
        self.stdout.write(f"Latest Seeking Alpha ratings date: {latest_quant_dump_date}")
        if not latest_quant_dump_date:
            self.stdout.write("No ratings data found")
            return

        types_to_update = get_types_pending_compilation(
            CompiledSAScore, latest_quant_dump_date, max_quant_types, write=self.stdout.write
        )

        # For each SA score type, get ALL the rating rows and compile the score.
        for current_type in types_to_update:
            compiled_type = (
                SARating.objects
                .filter(type=current_type)
                .values("sa_stock", "type")  # Grouping fields
                .annotate(count=Count("pk"), score=Sum(101 - F("rank")))
            )

            # Convert the query results to a list of CompiledSAScore objects for model insert.
            compiled_type_instances = []
            for entry in compiled_type:
                compiled_type_instances.append(CompiledSAScore(
                    sa_stock=SAStock.objects.get(pk=entry["sa_stock"]),
                    type=entry["type"],
                    score=entry["score"],
                    count=entry["count"],
                    latest_sa_ratings_date=latest_quant_dump_date
                ))

            # Update the Compiled Quant table (new symbols are added, existing ones updated).
            CompiledSAScore.objects.bulk_create(
                compiled_type_instances,
                update_conflicts=True,
                update_fields=["count", "score", "latest_sa_ratings_date"],
                unique_fields=["sa_stock", "type"],  # Fields to match existing rows that need updating
            )
            self.stdout.write(f"Compiled type: {SARating.TYPES[current_type]} ({compiled_type.count()} stock symbols)")

        self.stdout.write(self.style.SUCCESS(f"Compiled {len(types_to_update)} Seeking Alpha score types"))