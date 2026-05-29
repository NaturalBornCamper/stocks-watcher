from django.core.management import call_command
from django.core.management.base import BaseCommand

# Both halves of the pipeline read from / write to this directory.
SA_DUMPS_DIR = "data_dumps/seeking_alpha/"


class Command(BaseCommand):
    help = (
        "Standard monthly SA refresh: reorganise the raw SA dumps into one CSV "
        "per date (via sa_ratings_manipulations one_csv_per_date), then import "
        "those per-date CSVs into the database (via import_sa_ratings). "
        "Stops automatically if the first step fails."
    )

    def handle(self, *args, **opts):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "[1/2] Reorganising raw SA dumps into one CSV per date..."))
        call_command(
            "sa_ratings_manipulations", "one_csv_per_date",
            SA_DUMPS_DIR, SA_DUMPS_DIR,
        )

        self.stdout.write(self.style.MIGRATE_HEADING(
            "[2/2] Importing the per-date CSVs into the database..."))
        call_command("import_sa_ratings", f"{SA_DUMPS_DIR}*.csv")

        self.stdout.write(self.style.SUCCESS("Both steps done."))
