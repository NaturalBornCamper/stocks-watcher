from datetime import datetime

from django.core.mail import send_mail
from django.db.models import Q
from django.http import HttpResponse
from pyrotools.console import cprint, COLORS

from settings.base import EMAIL_DEFAULT_RECIPIENT
from utils.helpers import getenv
from constants import CURRENCY_USD, YAHOO_CAD_SUFFIX, CURRENCY_CAD, SEEKING_ALPHA_CAD_SUFFIX
from apps.watcher.models import Stock, Price, Alert
from apps.watcher.providers.alpha_vantage_rapidapi import AlphaVantageRapidAPI
from apps.watcher.providers.eodhd import EODHD
from apps.watcher.providers.marketstack import MarketStack
from apps.watcher.providers.mboum import Mboum

MAX_API_QUERY = 2


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
        MarketStack,  # 100/month, markets all over the world
        AlphaVantageRapidAPI,  # 5/minute, 500/day, adjusted close works with free
        #        financialmodelingprep,  # 250/day, US only, No provider setup yet, but account already made. Before alpha_vantage?
        Mboum,  # Rapid API, 500/month, have TSX also https://rapidapi.com/sparior/api/mboum-finance, 10 years data
        EODHD,  # 20/day, past year only, includes TSX
        # IEX,  # 7 days trial, expired
        # twelve_data, # RapidAPI, 800/day, 8 requests per minute, Canada only available on paid plan
        # finnhub, # 60/minute, worldwide stocks only paid
        # stockdata.org, # 100 per day, Can get Canada stocks details but no history
        # financialmodelingprep, # 250/day, US only
        # marketdata, 100/day, 1 year data, no Canada, strange format
        # AlphaVantage,  # 5/minute, 500/day, "adjusted close" for premium
    ]

    cad_apis = [
        MarketStack,  # 100/month, markets all over the world
        Mboum,  # Rapid API, 500/month, have TSX also https://rapidapi.com/sparior/api/mboum-finance, 10 years data
        # AlphaVantage,  # 5/minute, 500/day, adjusted close seems for premium
        EODHD,  # 20/day, past year only, includes Canada
    ]
    # TSX API: https://site.financialmodelingprep.com/developer/docs/tsx-prices-api/ (Didn't search correclty, first one I found, maybe better options)

    response = ""
    error_triggered = False
    max_api_query = int(request.GET.get("limit", MAX_API_QUERY))
    for stock in Stock.objects.filter(Q(date_last_fetch__lt=datetime.today()) | Q(date_last_fetch=None)).all()[
                 :max_api_query]:
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

