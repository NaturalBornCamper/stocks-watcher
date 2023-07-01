from datetime import datetime, timedelta

from django.db.models import Q
from django.http import HttpResponse
from pyrotools.console import cprint, COLORS

from watcher.models import Stock, Price, Alert
from watcher.providers import alpha_vantage, iex


def fetch_prices(request):
    # now = datetime.datetime.now()

    time_threshold = datetime.today() - timedelta(days=3)
    # queryset = Stock.objects.exclude(price__date__gt=time_threshold).order_by("-price__date").all()
    queryset = Stock.objects.order_by("-price__date").distinct("name")
    response = ""
    for stock in Stock.objects.filter(Q(date_last_fetch__lt=datetime.today()) | Q(date_last_fetch=None)).all()[:5]:
        # TODO Check if there are no dates for that stock. If so, then fetch &outputsize=full
        cprint(COLORS.BRIGHT_BLUE, f"Fetching \"{stock.name}\" prices, last fetch: {stock.date_last_fetch}")

        get_full_price_history = stock.date_last_fetch is None
        if type(result := alpha_vantage.fetch(stock, get_full_price_history)) is list:
            response += f"{stock.name} had {len(result)} rows to insert\n"
        else:
            # Error with Alpha Vantage API, try with IEX next
            response += f"{result}\n"
            if type(result := iex.fetch(stock, get_full_price_history)) is list:
                response += f"{stock.name} had {len(result)} rows to insert\n"
            else:
                response += f"{stock.name} error {result}\n"

        if type(result) is list:
            Price.objects.bulk_create(result, ignore_conflicts=True)
            stock.date_last_fetch = datetime.today()
            stock.save()

    # html = "<html><body>It is now %s.</body></html>" % now
    return HttpResponse(response)


# TODO Format prices for 2 decimals
# TODO Set mail sending
def send_alerts(request):
    for alert in Alert.objects.all():
        today_price = Price.objects.filter(stock=alert.stock).order_by("-date").first().close

        time_threshold = datetime.today() - timedelta(days=(alert.days if alert.days else 0))
        match alert.type:
            case Alert.TYPE_INTERVAL_CHEAPEST:
                if not Price.objects.filter(close__lte=today_price, date__gte=time_threshold).exists():
                    print(f"Price for {alert.stock.name} closed at {today_price}$ the cheapest in the past {alert.days} days")
            case Alert.TYPE_INTERVAL_HIGHEST:
                if not Price.objects.filter(close__gte=today_price, date__gte=time_threshold).exists():
                    print(f"Price for {alert.stock.name} closed at {today_price}$ the highest in the past {alert.days} days")
            case Alert.TYPE_LOWER_THAN:
                if today_price <= alert.value:
                    print(f"Price for {alert.stock.name} is lower than {alert.value}$ (closed at {today_price}$)")
            case Alert.TYPE_HIGHER_THAN:
                if today_price >= alert.value:
                    print(f"Price for {alert.stock.name} is higher than {alert.value}$ (closed at {today_price}$)")
            case _:
                pass

    return HttpResponse("yo")
