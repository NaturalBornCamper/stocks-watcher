from datetime import datetime, timedelta
from pprint import pprint

from django.core.mail import send_mail
from django.db.models import F, ExpressionWrapper, fields
from django.db.models import Q, Count, Sum, Value, Max
from django.forms import DurationField
from django.http import HttpResponse
from pyrotools.console import cprint, COLORS
from pyrotools.log import Log

from watcher.constants import CURRENCY_USD, YAHOO_CAD_SUFFIX, CURRENCY_CAD, SEEKING_ALPHA_CAD_PREFIX
from watcher.models import Stock, Price, Alert, Quant, CompiledQuant, QuantStock
from watcher.providers.alpha_vantage import AlphaVantage
from watcher.providers.alpha_vantage_rapidapi import AlphaVantageRapidAPI
from watcher.providers.eodhd import EODHD
from watcher.providers.marketstack import MarketStack
from watcher.providers.mboum import Mboum
from watcher.settings.base import EMAIL_DEFAULT_RECIPIENT
from watcher.utils.helpers import getenv

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
        AlphaVantage,  # 5/minute, 500/day, adjusted close seems for premium
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
        time_threshold = today - timedelta(days=(alert.days if alert.days else 0))
        subject = body = ""

        # TODO TYPE_INTERVAL_CHEAPEST and TYPE_INTERVAL_HIGHEST have a lot of duplicate code, could be refactored
        match alert.type:
            case Alert.TYPE_INTERVAL_CHEAPEST:
                price = (Price.objects.filter(stock=alert.stock, close__lte=last_price, date__lt=today)
                         .order_by("-date").first())
                if price is not None:
                    days_diff = (today.date() - price.date).days
                    if days_diff > alert.days:
                        subject = f"{alert.stock.name} is the cheapest it has been in {days_diff} days"
                        body = f"Price for {alert.stock.name} closed at {last_price}$ the cheapest in the past {days_diff} days"
                        body += f" (Last time was on {price.date})"
            case Alert.TYPE_INTERVAL_HIGHEST:
                price = (Price.objects.filter(stock=alert.stock, close__gte=last_price, date__lt=today)
                         .order_by("-date").first())
                if price is not None:
                    days_diff = (today.date() - price.date).days
                    if days_diff > alert.days:
                        subject = f"{alert.stock.name} is the highest it has been in {days_diff} days"
                        body = f"Price for {alert.stock.name} closed at {last_price}$ the highest in the past {days_diff} days"
                        body += f" (Last time was on {price.date})"
            case Alert.TYPE_LOWER_THAN:
                if last_price <= alert.value:
                    subject = f"{alert.stock.name} has reached less than {alert.value}$"
                    body = f"Price for {alert.stock.name} is lower than {alert.value}$ (closed at {last_price}$)"
            case Alert.TYPE_HIGHER_THAN:
                if last_price >= alert.value:
                    subject = f"{alert.stock.name} has reached more than {alert.value}$"
                    body = f"Price for {alert.stock.name} is higher than {alert.value}$ (closed at {last_price}$)"
            case _:
                pass

        if subject and body:
            yahoo_symbol = f"{alert.stock.symbol}{YAHOO_CAD_SUFFIX if alert.stock.currency == CURRENCY_CAD else ""}"
            sa_symbol = f"{alert.stock.symbol}{SEEKING_ALPHA_CAD_PREFIX if alert.stock.currency == CURRENCY_CAD else ""}"
            body += f"\n<a href=\"https://ca.finance.yahoo.com/quote/{yahoo_symbol}\">https://ca.finance.yahoo.com/quote/{yahoo_symbol}</a>"
            body += f"\n<a href=\"https://seekingalpha.com/symbol/{sa_symbol}\">https://seekingalpha.com/symbol/{sa_symbol}</a>"
            cprint(COLORS.BRIGHT_BLUE, subject)
            cprint(COLORS.BRIGHT_BLUE, body)
            send_email(
                to=alert.recipient if alert.recipient else EMAIL_DEFAULT_RECIPIENT,
                subject=subject,
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
    latest_quant_dump_date = Quant.objects.aggregate(latest_date=Max('date'))['latest_date']
    print(f"Latest quant dump: {latest_quant_dump_date}")
    if not latest_quant_dump_date:
        return HttpResponse("No quant data found")

    # Get quant types that have not been compiled yet (compilation date smaller than quant date)
    types_to_update = []
    for quant_type in Quant.TYPES.keys():
        # Exclude this quant type if it already has a compilation date greater than the latest date
        if CompiledQuant.objects.filter(latest_quant_date__gte=latest_quant_dump_date, type=quant_type).exists():
            print(f"Quant type already compiled: {quant_type}")
            continue

        # Don't fetch more types to compile than the max requested
        if len(types_to_update) >= max_quant_types:
            break
        types_to_update.append(quant_type)

    # For each quant type, get ALL the quant rows and compile the score
    for current_type in types_to_update:
        compiled_type = (
            Quant.objects
            .filter(type=current_type)
            .values("quant_stock", "type")  # Grouping fields
            .annotate(count=Count("pk"), score=Sum(101 - F('rank')))
        )

        # Convert the query results to a list of CompiledQuant objects for model insert
        compiled_type_instances = []
        for entry in compiled_type:
            compiled_type_instances.append(CompiledQuant(
                quant_stock=QuantStock.objects.get(pk=entry["quant_stock"]),
                type=entry["type"],
                score=entry["score"],
                count=entry["count"],
                latest_quant_date=latest_quant_dump_date
            ))

        # Update the Compiled Quant table (New stock symbols will be added, existing symbols will be updated)
        CompiledQuant.objects.bulk_create(
            compiled_type_instances,
            update_conflicts=True,
            update_fields=["count", "score", "latest_quant_date"],
            unique_fields=["quant_stock", "type"],  # Fields to match existing rows that need to updating
        )
        print(f"Compiled type: {Quant.TYPES[current_type]} ({compiled_type.count()} stock symbols)")

    return HttpResponse(f"Compiled {len(types_to_update)} quant types")


# TODO: NOT IMPLEMENTED YET, NO IDEA WHAT THIS DOES AT THE MOMENT, BUT IT CRASHES FOR SURE
def compile_quant_decay(request):
    max_quant_types = request.GET.get("limit", MAX_QUANT_TYPES_PER_RUN)

    # Calculate the current date and define the decay factor for each month
    current_date = datetime.now().date()
    print(current_date)

    # Calculate the difference in months
    # diff_in_months = ExpressionWrapper(
    #     expression=Func(F('date'), Value(current_date), function='AGE'),
    #     output_field=IntegerField()
    # )
    diff_in_months = ExpressionWrapper(
        F('date') - Value(current_date),
        output_field=DurationField()
    )

    # Calculate the number of months as an integer
    # num_months = Func(diff_in_months, Value(0), function='EXTRACT')

    latest_date = Quant.objects.aggregate(latest_date=Max('date'))['latest_date']
    pprint(latest_date)

    types_to_update = []
    for quant_type in Quant.TYPES.keys():
        if CompiledQuant.objects.filter(date__gt=latest_date, type=quant_type).exists():
            continue
        if len(types_to_update) >= max_quant_types:
            break
        types_to_update.append(quant_type)
    # pprint(types_to_update)

    # score_expression = 101 - F('rank') * (1 - (diff_in_months * DECAY_FACTOR))
    # score_expression = 101 - F('rank') * (1 - (num_months * DECAY_FACTOR))
    fuck_test = ExpressionWrapper(datetime.now().date() - F('date'), output_field=fields.DurationField)
    score_expression2 = 101 - F('rank') * (1 - (fuck_test * DECAY_FACTOR))
    score_expression = Sum(101 - F('rank'))
    diff = ExpressionWrapper(
        datetime.now().date() - F('date'),
        output_field=fields.DurationField()
    )
    for current_type in types_to_update:
        # try:
        compiled_type = (
            Quant.objects
            .values("seekingalpha_symbol", "type")
            .filter(type=current_type)
            # .annotate(diff=diff)
            # .annotate(count=Count("seekingalpha_symbol"), score=score_expression)
            # .annotate(count=Count("seekingalpha_symbol"), score=score_expression, diff_in_months=ExtractMonth('diff'))
            .annotate(count=Count("seekingalpha_symbol"), score=score_expression)
            .annotate(days_difference_delta=datetime.now().date() - F('date'))  # This returns a TimeDelta
            # .annotate(days_difference_delta=datetime.now().date() - F('date'))
            # .annotate(gg=ExpressionWrapper((datetime.now().date() - F('date')) * 100))
            # .annotate(gg=ExpressionWrapper((datetime.now().date() - F('date')) - F('rank'), output_field=DecimalField))
            # .annotate(fuck_test=score_expression2)
            .annotate(days_difference_delta_multiplied=ExpressionWrapper((datetime.now().date() - F('date')) * 123))
            # .annotate(days_difference_delta_multiplied=(datetime.now().date() - F('date'))*123)
            # .annotate(
            #     days_difference=Cast(
            #         Cast('JulianDay', datetime.now().date()) - Cast('JulianDay', F('date')), output_field=IntegerField())
            #         )
            .order_by("-score").all()
        )
        # except Exception as e:
        #     cprint(color=COLORS.RED, message=e.message)
        #     exit(0)
        try:
            print(compiled_type.count())
            pprint(compiled_type)
        except Exception as e:
            cprint(color=COLORS.RED, message=e.message)
            exit(0)
        #
        # compiled_type_instances = [CompiledQuant(**entry) for entry in compiled_type]
        # CompiledQuant.objects.bulk_create(
        #     compiled_type_instances,
        #     update_conflicts=True,
        #     update_fields=["count", "score"],
        #     unique_fields=["seekingalpha_symbol", "type"],
        # )

    return HttpResponse("yo")
