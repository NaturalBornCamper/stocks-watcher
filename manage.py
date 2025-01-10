#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


# TODO Find a way to not update stock last fetch date if updated before 5pm (closing price not available yet). Change field to datetime and look if less than 5pm instead?
# TODO Add watches in portfolio to quickly see the changes in one place (Compare every end of day with previous day and trigger if X% change or more)
def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "watcher.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
