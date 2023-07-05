#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


# Enter to the virtual environment.To enter to virtual environment, run the command: source /home/naturbl9/virtualenv/public_html/stocks-watcher.ashgun.com/3.9/bin/activate && cd /home/naturbl9/public_html/stocks-watcher.ashgun.com

# Option 1 (New one)
# Settings
# -public_html/stocks-watcher.ashgun.com/watcher application root in cPanel
# -passenger_wsgi.py in watcher folder
# Changes
# -Need to add sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), '..')) in wsgi.py
# -STATIC_ROOT = os.path.join(BASE_DIR, "../static") in production.py

# Option 2 (Old one) (Not sure if I can make static folder from root url
# Settings
# -public_html/stocks-watcher.ashgun.com application root in cPanel
# -passenger_wsgi.py in root folder
# Changes
# -Maybe STATIC_ROOT = os.path.join(BASE_DIR, "watcher/static") in production.py


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
