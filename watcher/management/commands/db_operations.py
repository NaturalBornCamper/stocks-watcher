from django.core.management.base import BaseCommand
from django.db import connection

from watcher.models import CompiledQuant, Quant, QuantStock, CompiledQuantDecay


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

        if operation == 'empty_quant_stock':
            truncate_and_reset_auto_increment(QuantStock._meta.db_table)
        elif operation == 'empty_quant':
            truncate_and_reset_auto_increment(Quant._meta.db_table)
        elif operation == 'empty_compiled_quant':
            truncate_and_reset_auto_increment(CompiledQuant._meta.db_table)
        elif operation == 'empty_compiled_quant_decay':
            truncate_and_reset_auto_increment(CompiledQuantDecay._meta.db_table)
        elif operation == 'empty_all_quant':
            truncate_and_reset_auto_increment(CompiledQuant._meta.db_table)
            truncate_and_reset_auto_increment(CompiledQuantDecay._meta.db_table)
            truncate_and_reset_auto_increment(Quant._meta.db_table)
            truncate_and_reset_auto_increment(QuantStock._meta.db_table)
