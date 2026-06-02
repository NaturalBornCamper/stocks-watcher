from datetime import datetime

from django.core.management.base import BaseCommand

from apps.watcher.models import Alert, Price
from apps.watcher.notifications import send_email
from constants import CURRENCY_CAD, SEEKING_ALPHA_CAD_SUFFIX, YAHOO_CAD_SUFFIX
from settings.base import EMAIL_DEFAULT_RECIPIENT


# Cronjob command: check every enabled alert against the latest stored price and
# email the ones that fired (cheapest/highest in N days, crossed a threshold, or
# moved by a percentage). Alerts set to fire once are disabled after they trigger.
# Usage
#  python manage.py send_alerts


# TODO Either tweak "cheapest in X days" to send a second alert once the stock price goes back up Y% after the low
#  or make a new type of alert
#  would be nice to be able to set the Y% value
#  re-adjust the new low if it goes down further
class Command(BaseCommand):
    help = "Check enabled price alerts against the latest prices and email the ones that fired."

    def handle(self, *args, **options):
        sent_alerts_count = 0
        for alert in Alert.objects.filter(enabled=True).all():
            last_price = Price.objects.filter(stock=alert.stock).order_by("-date").first()
            if not last_price:
                continue
            last_price = last_price.close
            self.stdout.write(f"{alert.stock.symbol} last close: {last_price}")

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
                self.stdout.write(subject)
                self.stdout.write(body)
                send_email(
                    to=alert.recipient if alert.recipient else EMAIL_DEFAULT_RECIPIENT,
                    subject=alert.name if alert.name else subject,
                    body=body,
                )

                if alert.disable_once_fired:
                    alert.enabled = False
                    alert.save()

                sent_alerts_count += 1

        self.stdout.write(self.style.SUCCESS(f"Sent {sent_alerts_count} alerts"))