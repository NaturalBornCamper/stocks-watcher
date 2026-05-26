import django.db.models.deletion
from django.db import migrations, models


SA_RATING_TYPE_CHOICES = [
    ("top_rated_overall", "Overall"),
    ("top_quant", "Quant"),
    ("top_dividend", "Dividend"),
    ("top_growth", "Growth"),
    ("top_value", "Value"),
    ("top_healthcare", "Healthcare"),
    ("top_utility", "Utility"),
    ("top_consumer_staples", "Consumer Staples"),
    ("top_technology", "Technology"),
    ("top_energy", "Energy"),
    ("top_materials", "Materials"),
    ("top_industrial", "Industrial"),
    ("top_communication", "Communication"),
    ("top_financial", "Financial"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("quant", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="compiledsascore",
            name="score",
            field=models.SmallIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="compiledsascoredecayed",
            name="score",
            field=models.SmallIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="CompiledSAScoreMomentum",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        choices=SA_RATING_TYPE_CHOICES,
                        max_length=255,
                    ),
                ),
                ("score", models.SmallIntegerField(default=0)),
                ("count", models.PositiveSmallIntegerField(default=0)),
                (
                    "latest_sa_ratings_date",
                    models.DateField(
                        verbose_name="Date of the latest Seeking Alpha ratings dump used for compilation"
                    ),
                ),
                (
                    "sa_stock",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="quant.sastock"
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Compiled sa scores momentum",
                "db_table": "quant_compiledsascorebase_momentum",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("sa_stock", "type"),
                        name="quant__compiled_score_momentum__unique__sa_stock__type",
                    )
                ],
            },
        ),
    ]