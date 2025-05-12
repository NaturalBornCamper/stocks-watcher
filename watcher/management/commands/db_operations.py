from django.core.management.base import BaseCommand
from django.db import connection

from quant.models import CompiledScore, SARating, SAStock, CompiledScoreDecayed


# Usage: python manage.py db_operations empty_table
# Usage: python manage.py db_operations empty_quant
# Usage: python manage.py db_operations empty_compiled_quant
# Usage: python manage.py db_operations empty_compiled_quant_decay
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
            truncate_and_reset_auto_increment(CompiledScore._meta.db_table)
        elif operation == 'empty_compiled_scores_decayed':
            truncate_and_reset_auto_increment(CompiledScoreDecayed._meta.db_table)
        elif operation == 'empty_all_quant':
            truncate_and_reset_auto_increment(CompiledScore._meta.db_table)
            truncate_and_reset_auto_increment(CompiledScoreDecayed._meta.db_table)
            truncate_and_reset_auto_increment(SARating._meta.db_table)
            truncate_and_reset_auto_increment(SAStock._meta.db_table)
