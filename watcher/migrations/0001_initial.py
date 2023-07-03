# Generated by Django 4.2.2 on 2023-07-03 03:47

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Stock",
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
                ("name", models.CharField(max_length=255)),
                (
                    "currency",
                    models.CharField(
                        choices=[("USD", "USD"), ("CAD", "CAD")], max_length=255
                    ),
                ),
                ("market", models.CharField(max_length=10)),
                ("symbol", models.CharField(max_length=10)),
                (
                    "google_symbol",
                    models.CharField(
                        blank=True,
                        max_length=10,
                        null=True,
                        verbose_name="Google symbol (if different)",
                    ),
                ),
                (
                    "yahoo_symbol",
                    models.CharField(
                        blank=True,
                        max_length=10,
                        null=True,
                        verbose_name="Yahoo symbol (if different)",
                    ),
                ),
                (
                    "seekingalpha_symbol",
                    models.CharField(
                        blank=True,
                        max_length=10,
                        null=True,
                        verbose_name="Seeking Alpha symbol (if different)",
                    ),
                ),
                (
                    "alphavantage_symbol",
                    models.CharField(
                        blank=True,
                        max_length=10,
                        null=True,
                        verbose_name="Alpha Vantage API symbol (if different)",
                    ),
                ),
                (
                    "iex_symbol",
                    models.CharField(
                        blank=True,
                        max_length=10,
                        null=True,
                        verbose_name="IEX Cloud API symbol (if different)",
                    ),
                ),
                (
                    "date_last_fetch",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="Last API call date (leave empty)",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Price",
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
                ("date", models.DateField()),
                ("low", models.DecimalField(decimal_places=2, max_digits=8)),
                ("high", models.DecimalField(decimal_places=2, max_digits=8)),
                ("open", models.DecimalField(decimal_places=2, max_digits=8)),
                ("close", models.DecimalField(decimal_places=2, max_digits=8)),
                ("volume", models.PositiveIntegerField()),
                (
                    "stock",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price",
                        to="watcher.stock",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Alert",
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
                    "name",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="Optional Name"
                    ),
                ),
                (
                    "type",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (1, "Cheapest In X Days"),
                            (2, "Most Expensive In X Days"),
                            (3, "Lower Than"),
                            (4, "Higher Than"),
                        ]
                    ),
                ),
                (
                    "days",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Number of days for interval alerts",
                    ),
                ),
                (
                    "value",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=8,
                        null=True,
                        verbose_name="Price in $ for value alerts",
                    ),
                ),
                (
                    "recipient",
                    models.EmailField(
                        blank=True,
                        max_length=254,
                        null=True,
                        verbose_name="Destination Email",
                    ),
                ),
                ("enabled", models.BooleanField(default=True)),
                (
                    "disable_once_fired",
                    models.BooleanField(
                        default=False, verbose_name="Disable alert after it was fired?"
                    ),
                ),
                (
                    "stock",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alert",
                        to="watcher.stock",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="price",
            constraint=models.UniqueConstraint(
                fields=("stock", "date"), name="unique_stock_date"
            ),
        ),
    ]
