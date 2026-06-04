from django.core.management.base import BaseCommand
from django.db import connection

from apps.quant.models import (
    CompiledSAScore,
    CompiledSAScoreDecayed,
    CompiledSAScoreMomentum,
    SARating,
    SAStock,
)


# Usage: python manage.py db_operations empty_sa_stocks
# Usage: python manage.py db_operations empty_sa_ratings
# Usage: python manage.py db_operations empty_compiled_scores
# Usage: python manage.py db_operations empty_compiled_scores_decayed
# Usage: python manage.py db_operations empty_compiled_scores_momentum
# Usage: python manage.py db_operations empty_all_quant

def truncate_and_reset_auto_increment(table_name):
    with connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {table_name};")
        cursor.execute(f"DELETE FROM sqlite_sequence WHERE name = '{table_name}';")


class Command(BaseCommand):
    help = 'Various database operations for development'

    def add_arguments(self, parser):
        parser.add_argument('operation', type=str, help='Database operation')

    def handle(self, *args, **options):
        operation = options['operation']

        if operation == 'empty_sa_stocks':
            truncate_and_reset_auto_increment(SAStock._meta.db_table)
        elif operation == 'empty_sa_ratings':
            truncate_and_reset_auto_increment(SARating._meta.db_table)
        elif operation == 'empty_compiled_scores':
            truncate_and_reset_auto_increment(CompiledSAScore._meta.db_table)
        elif operation == 'empty_compiled_scores_decayed':
            truncate_and_reset_auto_increment(CompiledSAScoreDecayed._meta.db_table)
        elif operation == 'empty_compiled_scores_momentum':
            truncate_and_reset_auto_increment(CompiledSAScoreMomentum._meta.db_table)
        elif operation == 'empty_all_quant':
            # Clear the derived score tables first, then ratings, then the stocks
            truncate_and_reset_auto_increment(CompiledSAScore._meta.db_table)
            truncate_and_reset_auto_increment(CompiledSAScoreDecayed._meta.db_table)
            truncate_and_reset_auto_increment(CompiledSAScoreMomentum._meta.db_table)
            truncate_and_reset_auto_increment(SARating._meta.db_table)
            truncate_and_reset_auto_increment(SAStock._meta.db_table)
        else:
            self.stderr.write(self.style.ERROR(f"Unknown operation: {operation}"))