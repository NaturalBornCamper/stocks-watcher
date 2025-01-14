from django.core.management.base import BaseCommand

from django.core.management.base import BaseCommand

from watcher.models import CompiledQuant, Quant


# Usage: python manage.py db_operations empty_quant
# Usage: python manage.py db_operations empty_compiled_quant


class Command(BaseCommand):
    help = 'Various database operations for development'

    def add_arguments(self, parser):
        parser.add_argument('operation', type=str, help='Database operation')

    def handle(self, *args, **options):
        operation = options['operation']

        if operation == 'empty_quant':
            Quant.objects.all().delete()
        elif operation == 'empty_compiled_quant':
            CompiledQuant.objects.all().delete()
