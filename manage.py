#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


# Enter to the virtual environment.To enter to virtual environment, run the command: source /home/naturbl9/virtualenv/public_html/stocks-watcher.ashgun.com/3.9/bin/activate && cd /home/naturbl9/public_html/stocks-watcher.ashgun.com

# TODO Primary key in Prices = stock_id, date. Add "update if exists" or ignore if exists
# NOTE to see usage left for stocks API: https://iexcloud.io/console/usage

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

# msft uclose, fclose, close same
# close*	number	Adjusted data for historical dates. Split adjusted only.
# fclose*	number	Fully adjusted for historical dates
# fhigh*	number	Fully adjusted for historical dates
# flow*	number	Fully adjusted for historical dates
# fopen*	number
# fvolume*	number
# high*	number	Adjusted data for historical dates. Split adjusted only.
# low*	number	Adjusted data for historical dates. Split adjusted only.
# open*	number	Adjusted data for historical dates. Split adjusted only.
# priceDate* date	string
# symbol* key	string	Associated symbol or ticker
# uclose*	number	Unadjusted data for historical dates
# uhigh*	number	Unadjusted data for historical dates
# ulow*	number	Unadjusted data for historical dates
# uopen*	number	Unadjusted data for historical dates
# uvolume*	number	Unadjusted data for historical dates
# volume*	number	Adjusted data for historical dates. Split adjusted only.
