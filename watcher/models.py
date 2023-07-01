from django.db import models
from django.db.models import UniqueConstraint


class Stock(models.Model):
    CURRENCY_USD = "USD"
    CURRENCY_CAD = "CAD"

    CURRENCIES = (
        (CURRENCY_USD, "USD"),
        (CURRENCY_CAD, "CAD"),
    )

    name = models.CharField(max_length=255)
    currency = models.CharField(max_length=255, choices=CURRENCIES)
    market = models.CharField(max_length=10)
    google_ticker = models.CharField(max_length=10)
    yahoo_ticker = models.CharField(max_length=10)
    seekingalpha_ticker = models.CharField(max_length=10)
    date_last_fetch = models.DateField(blank=True, null=True)

    # TODO display market:symbol as well in here + currency
    def __str__(self):
        return f"{self.name} - ({self.price.count()} prices - {self.alert.count()} alerts)"


class Price(models.Model):
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, db_index=True, related_name="price")
    date = models.DateField()
    low = models.FloatField()
    high = models.FloatField()
    open = models.FloatField()
    close = models.FloatField()
    volume = models.IntegerField()
    # dividend = models.FloatField()

    class Meta:
        constraints = [
            UniqueConstraint(
                name="unique_stock_date",
                fields=["stock", "date"]
            ),
        ]

    # TODO full display of prices in here
    def __str__(self):
        return f"{self.stock.name} {self.date}"


# TODO Add "disable" once fired?
# TODO Add optional name?
# TODO Add recipient email (Also have setting for default email in env variables)
class Alert(models.Model):
    TYPE_INTERVAL_CHEAPEST = 1
    TYPE_INTERVAL_HIGHEST = 2
    TYPE_LOWER_THAN = 3
    TYPE_HIGHER_THAN = 4

    ALERT_TYPES = (
        (TYPE_INTERVAL_CHEAPEST, "Cheapest In X Days"),
        (TYPE_INTERVAL_HIGHEST, "Most Expensive In X Days"),
        (TYPE_LOWER_THAN, "Lower Than"),
        (TYPE_HIGHER_THAN, "Higher Than"),
    )

    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, db_index=True, related_name="alert")
    type = models.PositiveSmallIntegerField(choices=ALERT_TYPES, blank=False)  # (cheapest_interval, lower_than, higher_than)
    days = models.PositiveSmallIntegerField(blank=True, null=True)  # (for use for example with cheapest_interval)
    value = models.FloatField(max_length=255, blank=True, null=True)  # (for use for example with lower_than, higher_than)

    # TODO full display of data in here
    def __str__(self):
        return f"{self.stock.name} {self.get_type_display()}"
