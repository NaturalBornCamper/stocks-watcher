from datetime import datetime, timedelta

from django.core.mail import send_mail
from django.db.models import Q
from django.http import HttpResponse
from pyrotools.console import cprint, COLORS

from watcher.models import Stock, Price, Alert
from watcher.providers import alpha_vantage, iex
from watcher.settings.base import EMAIL_DEFAULT_RECIPIENT
from watcher.utils import getenv

MAX_API_QUERY = 5


def send_email(to: str, subject: str, body: str):
    send_mail(
        subject,
        body,
        getenv("FROM_EMAIL"),
        [to],
        fail_silently=False,
    )


def fetch_prices(request):
    # APIS to try in order, until successful
    apis = [
        iex,
        alpha_vantage,
    ]

    time_threshold = datetime.today() - timedelta(days=3)
    response = ""
    error_triggered = False
    for stock in Stock.objects.filter(Q(date_last_fetch__lt=datetime.today()) | Q(date_last_fetch=None)).all()[
                 :MAX_API_QUERY]:
        get_full_price_history = stock.date_last_fetch is None

        response += f"Fetching \"{stock.name}\" prices, last fetch: {stock.date_last_fetch}\n"
        for api in apis:
            response += f"Using {api.API_NAME}\n"
            api_response = api.fetch(stock, get_full_price_history)
            if api_response["success"]:
                Price.objects.bulk_create(api_response["prices"], ignore_conflicts=True)
                response += f"{stock.name} {len(api_response['prices'])} rows inserted\n\n"
                stock.date_last_fetch = datetime.today()
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


def send_alerts(request):
    for alert in Alert.objects.filter(enabled=True).all():
        last_price = Price.objects.filter(stock=alert.stock).order_by("-date").first()
        if not last_price:
            continue
        last_price = last_price.close
        cprint(COLORS.CYAN, last_price)

        today = datetime.today()
        time_threshold = today - timedelta(days=(alert.days if alert.days else 0))
        subject = body = ""
        match alert.type:
            case Alert.TYPE_INTERVAL_CHEAPEST:
                if not Price.objects.filter(stock=alert.stock, close__lte=last_price, date__gte=time_threshold,
                                            date__lt=today).exists():
                    subject = f"{alert.stock.name} is the cheapest it has been in {alert.days} days"
                    body = f"Price for {alert.stock.name} closed at {last_price}$ the cheapest in the past {alert.days} days"
            case Alert.TYPE_INTERVAL_HIGHEST:
                if not Price.objects.filter(stock=alert.stock, close__gte=last_price, date__gt=time_threshold,
                                            date__lt=today).exists():
                    subject = f"{alert.stock.name} is the highest it has been in {alert.days} days"
                    body = f"Price for {alert.stock.name} closed at {last_price}$ the highest in the past {alert.days} days"
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

    return HttpResponse("yo")
