from django.db import models
from django.db.models import UniqueConstraint

from apps.watcher.models import Stock


class SAStock(models.Model):
    stock = models.OneToOneField(
        Stock, on_delete=models.SET_NULL, db_index=True, blank=True, null=True, related_name="sa_stock"
    )
    symbol = models.CharField(max_length=10, db_index=True, unique=True)
    name = models.CharField(max_length=255)


class SARating(models.Model):
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

    sa_stock = models.ForeignKey(SAStock, on_delete=models.CASCADE, db_index=True)
    date = models.DateField(blank=True, null=True, verbose_name="Year and month this data is from")
    type = models.CharField(max_length=255, choices=TYPES)
    rank = models.PositiveSmallIntegerField()
    quant = models.DecimalField(max_digits=3, decimal_places=2)
    rating_seeking_alpha = models.DecimalField(
        max_digits=3, decimal_places=2, blank=True, null=True, verbose_name="Seeking Alpha Rating"
    )
    rating_wall_street = models.DecimalField(
        max_digits=3, decimal_places=2, blank=True, null=True, verbose_name="Wall Street Rating"
    )
    market_cap_millions = models.FloatField(blank=True, null=True)
    dividend_yield = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    valuation = models.CharField(max_length=2)
    growth = models.CharField(max_length=2)
    profitability = models.CharField(max_length=2)
    momentum = models.CharField(max_length=2)
    eps_revision = models.CharField(max_length=2, blank=True, null=True)

    class Meta:
        constraints = [
            UniqueConstraint(name="quant__sa_rating__unique__date__type__sa_stock", fields=["date", "type", "sa_stock"]),
        ]

    @staticmethod
    def get_type_tuple(type_key: str) -> tuple:
        for sa_rating_type_tuple in SARating.TYPES:
            if type_key == sa_rating_type_tuple[0]:
                return sa_rating_type_tuple

        return SARating.TYPES[0]

    @staticmethod
    def get_type_display(key: str) -> str:
        for sa_rating_type_tuple in SARating.TYPES:
            if key == sa_rating_type_tuple[0]:
                return sa_rating_type_tuple[1]

        raise Exception(f"Invalid Seeking Alpha rating type requested: {key}")


class CompiledSAScoreBase(models.Model):
    sa_stock = models.ForeignKey(SAStock, on_delete=models.CASCADE, db_index=True)
    type = models.CharField(max_length=255, choices=SARating.TYPES, blank=False)
    score = models.PositiveSmallIntegerField(default=0)
    count = models.PositiveSmallIntegerField(default=0)
    latest_sa_ratings_date = models.DateField(verbose_name="Date of the latest Seeking Alpha ratings dump used for compilation")

    class Meta:
        abstract = True


class CompiledSAScore(CompiledSAScoreBase):
    class Meta:
        db_table = f"quant_{CompiledSAScoreBase._meta.model_name}_regular"
        constraints = [
            UniqueConstraint(name="quant__compiled_score__unique__sa_stock__type", fields=["sa_stock", "type"])
        ]


class CompiledSAScoreDecayed(CompiledSAScoreBase):
    DECAY_MONTHS = 3

    class Meta:
        db_table = f"quant_{CompiledSAScoreBase._meta.model_name}_decay"
        constraints = [
            UniqueConstraint(name="quant__compiled_score_decayed__unique__sa_stock__type", fields=["sa_stock", "type"])
        ]
