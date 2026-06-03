import time
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.watcher.models import Price, Stock
from apps.watcher.notifications import send_email
from apps.watcher.providers.alpha_vantage_rapidapi import AlphaVantageRapidAPI
from apps.watcher.providers.eodhd import EODHD
from apps.watcher.providers.marketstack import MarketStack
from apps.watcher.providers.mboum import Mboum
from apps.watcher.providers.yahoo import Yahoo
from constants import CURRENCY_USD
from settings.base import EMAIL_DEFAULT_RECIPIENT

MAX_API_QUERY = 5
MIN_SECONDS_BETWEEN_API_CALLS = 20


# TODO Find a way to not update stock last fetch date if updated before 5pm (closing price not available yet). Change field to datetime and look if less than 5pm instead?
#  This way if I call the cronjob before 5pm, it won't mark the current day as fetched?
# TODO Add API financialmodelingprep
#  https://financialmodelingprep.com/api/v3/historical-price-full/AAPL?apikey=d6IlFcraIFtrd0IDklzrPE9wf1T3X3b7
#  https://site.financialmodelingprep.com/developer/docs#daily-chart-charts
#  https://site.financialmodelingprep.com/developer/docs/pricing
#  Only US stocks, 250 calls per day, 5 years data
# TODO Add API FinancialData? Already made an account, not sure it included adjusted close (Or it's the default price)
# https://financialdata.net/pricing
# Might only be US stocks, 300 requests per day, need to use offset as only 300 per page
# Tested in Postman (already in project with API key), can't make CAD work
# To check all stocks and see if CAD stocks ever show up: https://financialdata.net/stocks/NVDA


# Cronjob command: download the latest daily prices for stocks that are due a fetch.
# Tries each price API in order until one succeeds, waiting a minimum gap between
# calls to respect rate limits. Skips weekends. Emails the full report if any API
# errored. Use --limit to cap how many stocks are queried in one run.
# Usage
#  python manage.py fetch_prices
#  python manage.py fetch_prices --limit 5      -> query at most 5 stocks this run


class Command(BaseCommand):
    help = "Download the latest daily prices for stocks that are due a fetch."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=MAX_API_QUERY,
            help="Max number of stocks to query in this run.",
        )

    def handle(self, *args, **options):
        max_api_query = options["limit"]

        today = datetime.today()
        if today.weekday() >= 5:
            self.stdout.write("Not a weekday, no need to insert today's prices")
            return

        # APIS IN STANDBY
        # polygon, # 5 calls per minute, 2 years historical, Don't have Canadian markets but it's on the roadmap
        # alpaca, # Contacted to see if they have CAD markets
        # tiingo, # 50/hour, 500 symbols per month, 1000/day, 30 years historical, TSX stocks are in USD, asked if can get in CAD

        # APIS to try in order, until successful
        usd_apis = [
            Yahoo,  # No key, no documented limit, adjusted close, includes TSX (.TO). Same source as the backtest
            AlphaVantageRapidAPI,  # 5/minute, 500/day, adjusted close works with free
            #        financialmodelingprep,  # 250/day, US only, No provider setup yet, but account already made. Before alpha_vantage?
            Mboum,  # Rapid API, 500/month, have TSX also https://rapidapi.com/sparior/api/mboum-finance, 10 years data
            EODHD,  # 20/day, past year only, includes TSX
            MarketStack,  # 100/month, markets all over the world
            # IEX,  # 7 days trial, expired
            # twelve_data, # RapidAPI, 800/day, 8 requests per minute, Canada only available on paid plan
            # finnhub, # 60/minute, worldwide stocks only paid
            # stockdata.org, # 100 per day, Can get Canada stocks details but no history
            # financialmodelingprep, # 250/day, US only
            # marketdata, 100/day, 1 year data, no Canada, strange format
            # AlphaVantage,  # 5/minute, 500/day, "adjusted close" for premium
        ]

        cad_apis = [
            Yahoo,  # No key, no documented limit, adjusted close, TSX via .TO suffix. Same source as the backtest
            Mboum,  # Rapid API, 500/month, have TSX also https://rapidapi.com/sparior/api/mboum-finance, 10 years data
            # AlphaVantage,  # 5/minute, 500/day, adjusted close seems for premium
            MarketStack,  # 100/month, markets all over the world
            EODHD,  # 20/day, past year only, includes Canada
        ]
        # TSX API: https://site.financialmodelingprep.com/developer/docs/tsx-prices-api/ (Didn't search correclty, first one I found, maybe better options)

        # Collect every line both for the live log (self.stdout) and for the error email body.
        report_lines = []

        def log(message):
            self.stdout.write(message)
            report_lines.append(message)

        error_triggered = False
        last_api_call_started_at = None
        due_stocks = Stock.objects.filter(
            Q(date_last_fetch__lt=datetime.today()) | Q(date_last_fetch=None)
        ).all()[:max_api_query]
        for stock in due_stocks:
            get_full_price_history = stock.date_last_fetch is None

            log(f"******Fetching \"{stock.name}\" prices, last fetch: {stock.date_last_fetch}******")
            for api in (usd_apis if stock.currency == CURRENCY_USD else cad_apis):
                if last_api_call_started_at is not None:
                    elapsed = time.monotonic() - last_api_call_started_at
                    sleep_seconds = MIN_SECONDS_BETWEEN_API_CALLS - elapsed
                    if sleep_seconds > 0:
                        time.sleep(sleep_seconds)

                last_api_call_started_at = time.monotonic()
                log(f"Using {api.API_NAME}")
                api_response = api.fetch(stock, get_full_price_history)
                if api_response["success"]:
                    Price.objects.bulk_create(api_response["prices"], ignore_conflicts=True)
                    log(f"{len(api_response['prices'])} rows inserted")
                    log("")
                    stock.date_last_fetch = today
                    stock.save()
                    break
                else:
                    error_triggered = True
                    log(f"Error on url {api_response['url']} ({api_response['status_code']})")
                    log(f"{api_response['message']}")
                    log("")

        if error_triggered:
            send_email(
                to=EMAIL_DEFAULT_RECIPIENT,
                subject="Stock Watcher error(s) when fetching prices",
                body="\n".join(report_lines),
            )