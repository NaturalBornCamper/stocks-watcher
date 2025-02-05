import re
from typing import Union

from django.contrib import admin, messages
from django.db.models import QuerySet, TextField
from django.forms import Textarea, HiddenInput, ModelChoiceField, ModelForm
from django.http import HttpResponseRedirect, HttpRequest
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe

from watcher.admin_filters import DateListFilter
from watcher.models import Stock, Price, Alert, QuantStock, Quant, CompiledQuant, CompiledQuantDecay


class AlertInline(admin.TabularInline):
    model = Alert
    extra = 0
    fields = ["name", "notes", "type", "days", "value"]

    # Makes the notes field less oversized
    formfield_overrides = {
        TextField: {"widget": Textarea(attrs={"rows": 2})},
    }

    # Renames some column headers verbose_name that are too long
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)

        if db_field.name == "days":
            field.label = "Minimum Days"
        elif db_field.name == "value":
            field.label = "Value"

        return field


class StockAdmin(admin.ModelAdmin):
    # Not sure this has any use, might be forgotten code, leaving it for a bit in case an issue arises
    # def get_queryset(self, request):
    #     qs = super().get_queryset(request)
    #     qs = qs.annotate(prices_count=Count("price"), alerts_count=Count("alert"))
    #     return qs

    # Deletes all prices for the selected stocks (useful if there's a stock split and they need to be reset)
    def delete_prices_from_selected_stocks(
            self, request: HttpRequest, queryset: QuerySet[Stock]
    ) -> HttpResponseRedirect:
        # Deletes all prices for the selected stocks
        for stock in queryset:
            stock.prices.all().delete()
        messages.success(request, "Prices deleted")
        return redirect(request.get_full_path())

    # Adds a link to the Quant details page of a specific stock
    def quant_stock_link(self, stock: Stock) -> str:
        if stock.quant_stock and stock.quant_stock.symbol:
            url = reverse("quant.stock", args=[stock.quant_stock.symbol])
            return mark_safe(f"<a href=\"{url}\" target=\"quant_{stock.quant_stock.symbol}\">View Quant</a>")
        return "-"

    # Adds a rollover (i) icon that displays game notes
    def notes_hint(self, stock: Stock) -> str:
        if stock.notes:
            # Replace newlines with <br> and add links
            notes = stock.notes.replace("\n", "<br>")
            notes = re.sub(r"(https?://\S+)", rf"<a href=\"\1\" target=\"{stock.pk}\">\1</a>", notes)
            return render_to_string("admin/notes.html", context={"notes": mark_safe(notes)})
        else:
            return ""

    # Adds percentage display for dividend yield if not null
    def dividend_yield_display(self, stock: Stock) -> str:
        return f"{stock.dividend_yield}%" if stock.dividend_yield else "-"

    # Prices count
    def prices_count(self, stock: Stock) -> str:
        return stock.prices.count()

    # Alerts count
    def alerts_count(self, stock: Stock) -> str:
        return stock.alerts.count()

    # Columns to display
    list_display = ["symbol", "quant_stock_link", "name", "notes_hint", "market", "currency",
                    "dividend_yield_display", "prices_count", "alerts_count"]

    # Quick actions
    actions = ["delete_prices_from_selected_stocks"]

    # Custom descriptions for quick actions
    delete_prices_from_selected_stocks.short_description = "Delete prices from selected stocks"

    # Show alerts on the Stock edit page
    inlines = [AlertInline]

    # Fields to search for "All words" (Default search behavior)
    search_fields = ["symbol", "name", "notes"]

    # Custom descriptions for columns
    notes_hint.short_description = "Notes"
    quant_stock_link.short_description = "Quant"
    dividend_yield_display.short_description = "Dividend yield"
    prices_count.short_description = "Prices count"
    alerts_count.short_description = "Alerts count"

    # Model fields to use for custom columns ordering
    notes_hint.admin_order_field = "notes"
    quant_stock_link.admin_order_field = "quant_stock"
    dividend_yield_display.admin_order_field = "dividend_yield"
    prices_count.admin_order_field = "prices_count"
    alerts_count.admin_order_field = "alerts_count"


class PriceAdmin(admin.ModelAdmin):
    list_display = ["stock", "date", "open", "low", "high", "close"]
    list_filter = ["stock"]
    search_fields = ["stock__symbol", "stock__name", "stock__notes"]


class AlertAdmin(admin.ModelAdmin):
    def notes_hint(self, alert: Alert) -> str:
        if alert.notes:
            # Replace newlines with <br> and add links
            notes = alert.notes.replace("\n", "<br>")
            notes = re.sub(r"(https?://\S+)", rf"<a href=\"\1\" target=\"{alert.pk}\">\1</a>", notes)
            return render_to_string("admin/notes.html", context={"notes": mark_safe(notes)})
        else:
            return ""

    def days_or_value(self, alert: Alert) -> Union[str, int]:
        if alert.type in [Alert.TYPE_INTERVAL_CHEAPEST, Alert.TYPE_INTERVAL_HIGHEST]:
            return alert.days
            # return f"{alert.days} days"
        else:
            return f"{alert.value}$"

    def disable_once_fired_display(self, alert: Alert) -> bool:
        return alert.disable_once_fired

    # Side filters
    list_filter = ["type", "stock"]

    # Fields to search for "All words" (Default search behavior)
    search_fields = ["stock__symbol", "stock__name", "name", "notes"]

    # Columns to display
    list_display = [
        "stock", "name", "notes_hint", "type", "days_or_value", "recipient", "enabled", "disable_once_fired_display"
    ]

    # Custom descriptions for columns
    notes_hint.short_description = "Notes"
    days_or_value.short_description = "Days/Value"
    disable_once_fired_display.short_description = "Disable after fired"

    # Model fields to use for custom columns ordering
    disable_once_fired_display.admin_order_field = "disable_once_fired"
    notes_hint.admin_order_field = "notes"


class QuantStockAdmin(admin.ModelAdmin):
    list_display = ["symbol", "name", "stock"]
    search_fields = ["symbol", "name"]


class QuantAdmin(admin.ModelAdmin):
    list_display = [
        "quant_stock__symbol", "quant_stock__name", "rank", "quant",
        "rating_seeking_alpha", "rating_wall_street", "type", "date"
    ]
    list_filter = ["type", DateListFilter]
    search_fields = ["quant_stock__symbol", "quant_stock__name", "type"]


class CompiledQuantAdmin(admin.ModelAdmin):
    list_display = ["quant_stock__symbol", "quant_stock__name", "score", "count", "type", "latest_quant_date"]
    list_filter = ["type"]
    search_fields = ["quant_stock__symbol", "quant_stock__name", "type"]


admin.site.register(Stock, StockAdmin)
admin.site.register(Price, PriceAdmin)
admin.site.register(Alert, AlertAdmin)
admin.site.register(QuantStock, QuantStockAdmin)
admin.site.register(Quant, QuantAdmin)
admin.site.register(CompiledQuant, CompiledQuantAdmin)
admin.site.register(CompiledQuantDecay, CompiledQuantAdmin)
