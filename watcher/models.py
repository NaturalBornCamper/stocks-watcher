from django.db import models
from django.db.models import UniqueConstraint

from watcher.settings.base import EMAIL_DEFAULT_RECIPIENT


# TODO Stock Category (optional)? Then I need a category editor? Might be uselful of others want to use it
class Stock(models.Model):
    CURRENCY_USD = "USD"
    CURRENCY_CAD = "CAD"

    CURRENCIES = (
        (CURRENCY_USD, "USD"),
        (CURRENCY_CAD, "CAD"),
    )

    name = models.CharField(max_length=255)
    currency = models.CharField(max_length=255, choices=CURRENCIES, default="USD")
    market = models.CharField(max_length=10, default="NASDAQ")
    symbol = models.CharField(max_length=10)
    google_symbol = models.CharField(max_length=10, blank=True, null=True, verbose_name="Google symbol (if different)")
    yahoo_symbol = models.CharField(max_length=10, blank=True, null=True, verbose_name="Yahoo symbol (if different)")
    seekingalpha_symbol = models.CharField(max_length=10, blank=True, null=True,
                                           verbose_name="Seeking Alpha symbol (if different)")
    alphavantage_symbol = models.CharField(max_length=10, blank=True, null=True,
                                           verbose_name="Alpha Vantage API symbol (if different)")
    iex_symbol = models.CharField(max_length=10, blank=True, null=True,
                                  verbose_name="IEX Cloud API symbol (if different)")
    date_last_fetch = models.DateField(blank=True, null=True, verbose_name="Last API call date (leave empty)")

    # Convert symbols to UPPERCASE
    def save(self, *args, **kwargs):
        self.symbol = self.symbol and self.symbol.upper()
        self.market = self.market and self.market.upper()
        self.google_symbol = self.google_symbol and self.google_symbol.upper()
        self.yahoo_symbol = self.yahoo_symbol and self.yahoo_symbol.upper()
        self.seekingalpha_symbol = self.seekingalpha_symbol and self.seekingalpha_symbol.upper()
        self.alphavantage_symbol = self.alphavantage_symbol and self.alphavantage_symbol.upper()
        self.iex_symbol = self.iex_symbol and self.iex_symbol.upper()
        super(Stock, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.market}: {self.symbol}) - {self.get_currency_display()} - ({self.price.count()} prices - {self.alert.count()} alerts)"

    class Meta:
        ordering = ["name"]

class Price(models.Model):
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, db_index=True, related_name="price")
    date = models.DateField()
    low = models.DecimalField(max_digits=8, decimal_places=2)
    high = models.DecimalField(max_digits=8, decimal_places=2)
    open = models.DecimalField(max_digits=8, decimal_places=2)
    close = models.DecimalField(max_digits=8, decimal_places=2)
    volume = models.PositiveIntegerField()

    # dividend = models.FloatField()

    class Meta:
        constraints = [
            UniqueConstraint(
                name="unique_stock_date",
                fields=["stock", "date"]
            ),
        ]
        ordering = ["-date", "stock"]

    def __str__(self):
        return f"{self.stock.name} - {self.date} - Open:{self.open}$ - Low:{self.low}$ - High:{self.high}$ - Close:{self.close}$"


# Maybe find a way to make less alerts? Combine highest and lowest in X days maybe?
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
    name = models.CharField(max_length=255, blank=True, verbose_name="Optional Name")
    type = models.PositiveSmallIntegerField(choices=ALERT_TYPES, blank=False)
    days = models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Number of days for interval alerts")
    value = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True,
                                verbose_name="Price in $ for value alerts")
    recipient = models.EmailField(blank=True, null=True, verbose_name="Destination Email")
    enabled = models.BooleanField(default=True)
    disable_once_fired = models.BooleanField(default=False, verbose_name="Disable alert after it was fired?")

    def __str__(self):
        bob = f"{self.value}$" if self.value else f"({self.days} days)"
        recipient = self.recipient if self.recipient else EMAIL_DEFAULT_RECIPIENT
        return self.name if self.name else f"{self.stock.name} - {self.get_type_display()} {bob} - Send to {recipient}"

    class Meta:
        ordering = ["stock", "type"]
