from django.db import models
from django.db.models import UniqueConstraint

from watcher.settings.base import EMAIL_DEFAULT_RECIPIENT


# TODO Stock Category (optional)? Then I need a category editor? Might be uselful of others want to use it
# TODO Find a way to update dividend yield automatically?
class Stock(models.Model):
    CURRENCY_USD = "USD"
    CURRENCY_CAD = "CAD"

    CURRENCIES = [
        (CURRENCY_USD, "USD"),
        (CURRENCY_CAD, "CAD"),
    ]

    name = models.CharField(max_length=255)
    currency = models.CharField(max_length=255, choices=CURRENCIES, default=CURRENCY_USD)
    market = models.CharField(max_length=10, default="NASDAQ")
    symbol = models.CharField(max_length=10)
    google_symbol = models.CharField(max_length=10, blank=True, null=True, verbose_name="Google symbol (if different)")
    yahoo_symbol = models.CharField(max_length=10, blank=True, null=True, verbose_name="Yahoo symbol (if different)")
    seekingalpha_symbol = models.CharField(max_length=10, blank=True, null=True,
                                           verbose_name="Seeking Alpha symbol (if different)")
    marketstack_symbol = models.CharField(max_length=10, blank=True, null=True,
                                          verbose_name="Marketstack API symbol (if different)")
    date_last_fetch = models.DateField(blank=True, null=True, verbose_name="Last API call date (leave empty)")
    dividend_yield = models.DecimalField(max_digits=4, decimal_places=2, blank=True, null=False, default=0)

    # Convert symbols to UPPERCASE
    def save(self, *args, **kwargs):
        self.symbol = self.symbol and self.symbol.upper()
        self.market = self.market and self.market.upper()
        self.google_symbol = self.google_symbol and self.google_symbol.upper()
        self.yahoo_symbol = self.yahoo_symbol and self.yahoo_symbol.upper()
        self.seekingalpha_symbol = self.seekingalpha_symbol and self.seekingalpha_symbol.upper()
        self.marketstack_symbol = self.marketstack_symbol and self.marketstack_symbol.upper()
        super(Stock, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.market}: {self.symbol}) - {self.get_currency_display()} - ({self.price.count()} prices - {self.alert.count()} alerts) - {self.dividend_yield}% dividend"

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


# TODO Change "lowest in X" days alert, to activate "secondary" alert when stock goes up X% after a low.
#  Then I know to buy when it's going back up instead of buying when it keeps going lower and lower
#  Important: If next day is even lower, it must use this new value as the base for the X% change
#  Maybe find a way to make less alerts? Combine highest and lowest in X days maybe?
class Alert(models.Model):
    TYPE_INTERVAL_CHEAPEST = 1
    TYPE_INTERVAL_HIGHEST = 2
    TYPE_LOWER_THAN = 3
    TYPE_HIGHER_THAN = 4

    TYPES = [
        (TYPE_INTERVAL_CHEAPEST, "Cheapest In X Days"),
        (TYPE_INTERVAL_HIGHEST, "Most Expensive In X Days"),
        (TYPE_LOWER_THAN, "Lower Than"),
        (TYPE_HIGHER_THAN, "Higher Than"),
    ]

    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, db_index=True, related_name="alert")
    name = models.CharField(max_length=255, blank=True, verbose_name="Optional Name")
    type = models.PositiveSmallIntegerField(choices=TYPES, blank=False)
    days = models.PositiveSmallIntegerField(blank=True, null=True,
                                            verbose_name="Minimum number of days for interval alerts")
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


# TODO Add company name to model, then import it in import_quant
class Quant(models.Model):
    TYPE_TOP_RATED_OVERALL = "top_rated_overall"
    TYPE_QUANT = "top_quant"
    TYPE_DIVIDEND = "top_dividend"
    TYPE_GROWTH = "top_growth"
    TYPE_VALUE = "top_value"
    TYPE_HEALTHCARE = "top_healthcare"
    TYPE_UTILITY = "top_utility"
    TYPE_CONSUMER_STAPLES = "top_consumer_staples"
    TYPE_TECHNOLOGY = "top_technology"
    TYPE_ENERGY = "top_energy"
    TYPE_MATERIALS = "top_materials"
    TYPE_INDUSTRIAL = "top_industrial"
    TYPE_COMMUNICATION = "top_communication"
    TYPE_FINANCIAL = "top_financial"

    TYPES = {
        TYPE_TOP_RATED_OVERALL: "Overall",
        TYPE_QUANT: "Quant",
        TYPE_DIVIDEND: "Dividend",
        TYPE_GROWTH: "Growth",
        TYPE_VALUE: "Value",
        TYPE_HEALTHCARE: "Healthcare",
        TYPE_UTILITY: "Utility",
        TYPE_CONSUMER_STAPLES: "Consumer Staples",
        TYPE_TECHNOLOGY: "Technology",
        TYPE_ENERGY: "Energy",
        TYPE_MATERIALS: "Materials",
        TYPE_INDUSTRIAL: "Industrial",
        TYPE_COMMUNICATION: "Communication",
        TYPE_FINANCIAL: "Financial",
    }

    date = models.DateField(blank=True, null=True, verbose_name="Year and month this data is from")
    type = models.CharField(max_length=255, choices=TYPES)
    rank = models.PositiveSmallIntegerField()
    seekingalpha_symbol = models.CharField(max_length=10)
    quant = models.DecimalField(max_digits=3, decimal_places=2)
    rating_seeking_alpha = models.DecimalField(max_digits=3, decimal_places=2, blank=True, null=True)
    rating_wall_street = models.DecimalField(max_digits=3, decimal_places=2, blank=True, null=True)
    market_cap_millions = models.FloatField(blank=True, null=True)
    dividend_yield = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    valuation = models.CharField(max_length=2)
    growth = models.CharField(max_length=2)
    profitability = models.CharField(max_length=2)
    momentum = models.CharField(max_length=2)
    eps_revision = models.CharField(max_length=2, blank=True, null=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                name="unique_quant_date_type_symbol",
                fields=["date", "type", "seekingalpha_symbol"]
            ),
        ]

    @staticmethod
    def get_type_tuple(type_key: str) -> tuple:
        for quant_type_tuple in Quant.TYPES:
            if type_key == quant_type_tuple[0]:
                return quant_type_tuple

        return Quant.TYPES[0]

    @staticmethod
    def get_type_display(key: str) -> str:
        for quant_type_tuple in Quant.TYPES:
            if key == quant_type_tuple[0]:
                return quant_type_tuple[1]

        raise Exception(f"Invalid Quant type requested: {key}")


class CompiledQuant(models.Model):
    seekingalpha_symbol = models.CharField(max_length=10, blank=False)
    type = models.CharField(max_length=255, choices=Quant.TYPES, blank=False)
    score = models.PositiveSmallIntegerField(default=0)
    count = models.PositiveSmallIntegerField(default=0)
    compilation_date = models.DateField(auto_now=True, verbose_name="Date this row was compiled")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['seekingalpha_symbol', 'type'], name='pk_compiledquant')
        ]
