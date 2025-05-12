from datetime import datetime, timedelta, date
from logging import lastResort

from django.core.mail import send_mail
from django.db.models import F
from django.db.models import Q, Count, Sum, Max
from django.http import HttpResponse
from pyrotools.console import cprint, COLORS
from pyrotools.log import Log

from settings.base import EMAIL_DEFAULT_RECIPIENT
from utils.helpers import getenv
from watcher.constants import CURRENCY_USD, YAHOO_CAD_SUFFIX, CURRENCY_CAD, SEEKING_ALPHA_CAD_SUFFIX
from watcher.models import Stock, Price, Alert
from quant.models import SAStock, SARating, CompiledScore, CompiledScoreDecayed
from watcher.providers.alpha_vantage import AlphaVantage
from watcher.providers.alpha_vantage_rapidapi import AlphaVantageRapidAPI
from watcher.providers.eodhd import EODHD
from watcher.providers.marketstack import MarketStack
from watcher.providers.mboum import Mboum

MAX_API_QUERY = 5
MAX_QUANT_TYPES_PER_RUN = 5
DECAY_FACTOR = 0.05


def send_email(to: str, subject: str, body: str):
    send_mail(
        subject,
        body,
        getenv("FROM_EMAIL"),
        [to],
        fail_silently=False,
        html_message=body.replace("\n", "<br>"),
    )


# Returns the amount of months between two dates (dates must be the first of the month)
def get_distance_in_months(earliest_date: datetime.date, latest_date: datetime.date) -> int:
    if not isinstance(earliest_date, date) or not isinstance(latest_date, date):
        raise TypeError(f"Dates must be datetime.date objects. Types: {type(earliest_date)}, {type(latest_date)}")

    if earliest_date.day != 1 or latest_date.day != 1:
        raise ValueError(f"Dates must be the first of the month. date1: {earliest_date}, date2: {latest_date}")

    months = (latest_date.year - earliest_date.year) * 12 + (latest_date.month - earliest_date.month)
    return months


# Goes back <months_to_rewind> in the past from a given date and returns the first day of that month
def rewind_months(from_date: date, months_to_rewind) -> date:
    adjusted_year, adjusted_month = from_date.year, from_date.month - months_to_rewind
    if adjusted_month < 1:
        adjusted_year -= 1
        adjusted_month += 12

    return date(adjusted_year, adjusted_month, 1)


# TODO Find a way to not update stock last fetch date if updated before 5pm (closing price not available yet). Change field to datetime and look if less than 5pm instead?
#  This way if I call the cronjob before 5pm, it won't mark the current day as fetched?
# TODO Add API financialmodelingprep
#  https://financialmodelingprep.com/api/v3/historical-price-full/AAPL?apikey=d6IlFcraIFtrd0IDklzrPE9wf1T3X3b7
#  https://site.financialmodelingprep.com/developer/docs#daily-chart-charts
#  https://site.financialmodelingprep.com/developer/docs/pricing
#  Only US stocks, 250 calls per day, 5 years data

def fetch_prices(request):
    # APIS IN STANDBY
    # polygon, # 5 calls per minute, 2 years historical, Don't have Canadian markets but it's on the roadmap
    # alpaca, # Contacted to see if they have CAD markets
    # tiingo, # 50/hour, 500 symbols per month, 1000/day, 30 years historical, TSX stocks are in USD, asked if can get in CAD

    today = datetime.today()
    if today.weekday() >= 5:
        return HttpResponse("Not a weekday, no need to insert today's prices")

    # APIS to try in order, until successful
    usd_apis = [
        AlphaVantageRapidAPI,  # 5/minute, 500/day, adjusted close works with free
        #        financialmodelingprep,  # 250/day, US only, No provider setup yet, but account already made. Before alpha_vantage?
        Mboum,  # Rapid API, 500/month, have TSX also https://rapidapi.com/sparior/api/mboum-finance, 10 years data
        EODHD,  # 20/day, past year only, includes TSX
        MarketStack,  # 100/month, markets all over the world, only 1 year data
        # IEX,  # 7 days trial, expired
        # twelve_data, # RapidAPI, 800/day, 8 requests per minute, Canada only available on paid plan
        # finnhub, # 60/minute, worldwide stocks only paid
        # stockdata.org, # 100 per day, Can get Canada stocks details but no history
        # financialmodelingprep, # 250/day, US only
        # marketdata, 100/day, 1 year data, no Canada, strange format
        # AlphaVantage,  # 5/minute, 500/day, "adjusted close" for premium
    ]

    cad_apis = [
        Mboum,  # Rapid API, 500/month, have TSX also https://rapidapi.com/sparior/api/mboum-finance, 10 years data
        # AlphaVantage,  # 5/minute, 500/day, adjusted close seems for premium
        EODHD,  # 20/day, past year only, includes Canada
        MarketStack,  # 100/month, markets all over the world, only 1 year data
    ]
    # TSX API: https://site.financialmodelingprep.com/developer/docs/tsx-prices-api/ (Didn't search correclty, first one I found, maybe better options)

    response = ""
    error_triggered = False
    for stock in Stock.objects.filter(Q(date_last_fetch__lt=datetime.today()) | Q(date_last_fetch=None)).all()[
                 :MAX_API_QUERY]:
        get_full_price_history = stock.date_last_fetch is None

        response += f"******Fetching \"{stock.name}\" prices, last fetch: {stock.date_last_fetch}******\n"
        for api in (usd_apis if stock.currency == CURRENCY_USD else cad_apis):
            response += f"Using {api.API_NAME}\n"
            api_response = api.fetch(stock, get_full_price_history)
            if api_response["success"]:
                Price.objects.bulk_create(api_response["prices"], ignore_conflicts=True)
                response += f"{len(api_response['prices'])} rows inserted\n\n"
                stock.date_last_fetch = today
                stock.save()
                break
            else:
                error_triggered = True
                response += f"Error on url {api_response['url']} ({api_response['status_code']})\n"
                response += f"{api_response['message']}\n\n"

    if error_triggered:
        send_email(
            to=EMAIL_DEFAULT_RECIPIENT,
            subject="Stock Watcher error(s) when fetching prices",
            body=response,
        )
    return HttpResponse(response)


# TODO Either tweak "cheapest in X days" to send a second alert once the stock price goes back up Y% after the low
#  or make a new type of alert
#  would be nice to be able to set the Y% value
#  re-adjust the new low if it goes down further
def send_alerts(request):
    sent_alerts_count = 0
    for alert in Alert.objects.filter(enabled=True).all():
        last_price = Price.objects.filter(stock=alert.stock).order_by("-date").first()
        if not last_price:
            continue
        last_price = last_price.close
        cprint(COLORS.CYAN, last_price)

        today = datetime.today()
        subject = body = ""

        # TODO TYPE_INTERVAL_CHEAPEST and TYPE_INTERVAL_HIGHEST have a lot of duplicate code, could be refactored
        match alert.type:
            case Alert.TYPE_INTERVAL_CHEAPEST:
                price = (Price.objects.filter(stock=alert.stock, close__lte=last_price, date__lt=today)
                         .order_by("-date").first())
                if price is not None:
                    days_diff = (today.date() - price.date).days
                    if days_diff > alert.days:
                        subject = f"{alert.stock.name}({alert.stock.symbol}) is the cheapest it has been in {days_diff} days"
                        body = f"Price for {alert.stock.name} closed at {last_price}$ the cheapest in the past {days_diff} days"
                        body += f" (Last time was on {price.date})"
            case Alert.TYPE_INTERVAL_HIGHEST:
                price = (Price.objects.filter(stock=alert.stock, close__gte=last_price, date__lt=today)
                         .order_by("-date").first())
                if price is not None:
                    days_diff = (today.date() - price.date).days
                    if days_diff > alert.days:
                        subject = f"{alert.stock.name}({alert.stock.symbol}) is the highest it has been in {days_diff} days"
                        body = f"Price for {alert.stock.name} closed at {last_price}$ the highest in the past {days_diff} days"
                        body += f" (Last time was on {price.date})"
            case Alert.TYPE_LOWER_THAN:
                if last_price <= alert.value:
                    subject = f"{alert.stock.name}({alert.stock.symbol}) has reached less than {alert.value}$"
                    body = f"Price for {alert.stock.name} is lower than {alert.value}$ (closed at {last_price}$)"
            case Alert.TYPE_HIGHER_THAN:
                if last_price >= alert.value:
                    subject = f"{alert.stock.name}({alert.stock.symbol}) has reached more than {alert.value}$"
                    body = f"Price for {alert.stock.name} is higher than {alert.value}$ (closed at {last_price}$)"
            case Alert.TYPE_PERCENTAGE_PRICE_CHANGE:
                previous_price = Price.objects.filter(stock=alert.stock, date__lt=today).order_by("-date").first()
                if previous_price is not None:
                    percent_change = ((last_price - previous_price.close) / previous_price.close) * 100
                    if abs(percent_change) >= alert.value:
                        change_direction = "gained" if percent_change > 0 else "lost"
                        subject = f"{alert.stock.name}({alert.stock.symbol}) has {change_direction} {percent_change:.1f}%"
                        body = f"Price for {alert.stock.name} {change_direction} {percent_change:.1f}% (closed at {last_price}$)"
            case _:
                pass

        if subject and body:
            yahoo_symbol = f"{alert.stock.symbol}{YAHOO_CAD_SUFFIX if alert.stock.currency == CURRENCY_CAD else ''}"
            sa_symbol = f"{alert.stock.symbol}{SEEKING_ALPHA_CAD_SUFFIX if alert.stock.currency == CURRENCY_CAD else ''}"
            body += f"\n<a href=\"https://ca.finance.yahoo.com/quote/{yahoo_symbol}\">https://ca.finance.yahoo.com/quote/{yahoo_symbol}</a>"
            body += f"\n<a href=\"https://seekingalpha.com/symbol/{sa_symbol}\">https://seekingalpha.com/symbol/{sa_symbol}</a>"
            body += f"\n\n{alert.notes}"
            cprint(COLORS.BRIGHT_BLUE, subject)
            cprint(COLORS.BRIGHT_BLUE, body)
            send_email(
                to=alert.recipient if alert.recipient else EMAIL_DEFAULT_RECIPIENT,
                subject=alert.name if alert.name else subject,
                body=body,
            )

            if alert.disable_once_fired:
                alert.enabled = False
                alert.save()

            sent_alerts_count += 1

    return HttpResponse(f"Sent {sent_alerts_count} alerts")


def compile_quant(request):
    Log.d("TODO replace all prints with logging")
    max_quant_types = int(request.GET.get("limit", MAX_QUANT_TYPES_PER_RUN))

    # Get the date of the latest quant data from Seeking Alpha dumps
    latest_quant_dump_date = SARating.objects.aggregate(latest_date=Max('date'))['latest_date']
    print(f"Latest quant dump: {latest_quant_dump_date}")
    if not latest_quant_dump_date:
        return HttpResponse("No quant data found")

    # Get quant types that have not been compiled yet (compilation date smaller than quant date)
    types_to_update = []
    for quant_type in SARating.TYPES.keys():
        # Exclude this quant type if it already has a compilation date greater than the latest date
        if CompiledScore.objects.filter(latest_quant_date__gte=latest_quant_dump_date, type=quant_type).exists():
            print(f"Quant type already compiled: {quant_type}")
            continue

        # Don't fetch more types to compile than the max requested
        if len(types_to_update) >= max_quant_types:
            break
        types_to_update.append(quant_type)

    # For each quant type, get ALL the quant rows and compile the score
    for current_type in types_to_update:
        compiled_type = (
            SARating.objects
            .filter(type=current_type)
            .values("sa_stock", "type")  # Grouping fields
            .annotate(count=Count("pk"), score=Sum(101 - F('rank')))
        )

        # Convert the query results to a list of CompiledScore objects for model insert
        compiled_type_instances = []
        for entry in compiled_type:
            compiled_type_instances.append(CompiledScore(
                sa_stock=SAStock.objects.get(pk=entry["sa_stock"]),
                type=entry["type"],
                score=entry["score"],
                count=entry["count"],
                latest_quant_date=latest_quant_dump_date
            ))

        # Update the Compiled Quant table (New stock symbols will be added, existing symbols will be updated)
        CompiledScore.objects.bulk_create(
            compiled_type_instances,
            update_conflicts=True,
            update_fields=["count", "score", "latest_quant_date"],
            unique_fields=["sa_stock", "type"],  # Fields to match existing rows that need to updating
        )
        print(f"Compiled type: {SARating.TYPES[current_type]} ({compiled_type.count()} stock symbols)")

    return HttpResponse(f"Compiled {len(types_to_update)} quant types")


def compile_quant_decay(request):
    max_quant_types = int(request.GET.get("limit", MAX_QUANT_TYPES_PER_RUN))
    decay_months = int(request.GET.get("decay_months", CompiledScoreDecayed.DECAY_MONTHS))
    print(f"Max decay distance: {decay_months}")

    # Builds the decay factor list of length (max_decay_distance + 1). For example:
    # max_decay_distance 3 => [1.0, 0.75, 0.5, 0.25]
    # max_decay_distance 1 => [1.0, 0.5]
    decay_factors = [1.0 - (i / (decay_months)) for i in range(decay_months)]
    print(f"Decay factors: {decay_factors}")

    latest_quant_dump_date = SARating.objects.aggregate(latest_date=Max('date'))['latest_date']
    if not latest_quant_dump_date:
        return HttpResponse("No quant data found")
    print(f"Latest quant dump: {latest_quant_dump_date}")

    earliest_quant_date = rewind_months(latest_quant_dump_date, decay_months - 1)

    # Build array of quant types to compile
    types_to_update = []
    for quant_type in SARating.TYPES.keys():
        if CompiledScoreDecayed.objects.filter(latest_quant_date__gte=latest_quant_dump_date, type=quant_type).exists():
            print(f"Quant type already compiled: {quant_type}")
            continue
        if len(types_to_update) >= max_quant_types:
            break
        types_to_update.append(quant_type)

    compiled_quants_with_decay = {}
    for current_type in types_to_update:
        print(f"Processing quant type: {SARating.TYPES[current_type]}")

        # Clear old values
        CompiledScoreDecayed.objects.filter(type=current_type).delete()

        # Get all quant data with given type and date > maximum months back
        for quant in (SARating.objects.filter(type=current_type, date__gte=earliest_quant_date).order_by("date")):
            decay_factor = decay_factors[get_distance_in_months(quant.date, latest_quant_dump_date)]

            # Add sa_stock to the dictionary if it doesn't exist yet
            if quant.sa_stock not in compiled_quants_with_decay:
                compiled_quants_with_decay[quant.sa_stock] = CompiledScoreDecayed(
                    sa_stock=quant.sa_stock,
                    type=current_type,
                    score=0,
                    count=0,
                    latest_quant_date=latest_quant_dump_date
                )

            # Calculate the new decayed score and append values for debug
            compiled_quants_with_decay[quant.sa_stock].count += 1
            compiled_quants_with_decay[quant.sa_stock].score += int((101 - quant.rank) * decay_factor)

    if compiled_quants_with_decay:
        CompiledScoreDecayed.objects.bulk_create(compiled_quants_with_decay.values())

    return HttpResponse(f"Compiled {len(types_to_update)} quant types")
