from typing import Union

from django.contrib import admin
from django.db.models import Count
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.conf import settings

from watcher.admin_filters import DateListFilter
from watcher.models import Stock, Price, Alert, QuantStock, Quant, CompiledQuant


class StockAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.annotate(prices_count=Count('price'), alerts_count=Count('alert'))
        return qs

    def prices_count(self, stock: Stock) -> str:
        return stock.price.count()

    def alerts_count(self, stock: Stock) -> str:
        return stock.alert.count()

    def dividend_yield_display(self, stock: Stock) -> str:
        return f"{stock.dividend_yield}%" if stock.dividend_yield else "-"

    def quant_stock_link(self, stock: Stock) -> str:
        if stock.quant_stock and stock.quant_stock.symbol:
            url = reverse('quant.stock', args=[stock.quant_stock.symbol])
            return mark_safe(f"<a href=\"{url}\" target=\"quant_{stock.quant_stock.symbol}\">View Quant</a>")
        return "-"

    quant_stock_link.short_description = "Quant"
    quant_stock_link.admin_order_field = "quant_stock"
    dividend_yield_display.short_description = "Dividend yield"
    dividend_yield_display.admin_order_field = "dividend_yield"
    prices_count.short_description = "Prices count"
    prices_count.admin_order_field = "prices_count"
    alerts_count.short_description = "Alerts count"
    alerts_count.admin_order_field = "alerts_count"
    list_display = ["symbol", "quant_stock_link", "name", "market", "currency", "dividend_yield_display",
                    "prices_count", "alerts_count"]
    search_fields = ["symbol", "name", "notes"]


class PriceAdmin(admin.ModelAdmin):
    list_display = ["stock", "date", "open", "low", "high", "close"]
    list_filter = ["stock"]
    search_fields = ["stock__symbol", "stock__name", "stock__notes"]


class AlertAdmin(admin.ModelAdmin):
    def days_or_value(self, alert: Alert) -> Union[str, int]:
        if alert.type in [Alert.TYPE_INTERVAL_CHEAPEST, Alert.TYPE_INTERVAL_HIGHEST]:
            return alert.days
            # return f"{alert.days} days"
        else:
            return f"{alert.value}$"

    def disable_once_fired_display(self, alert: Alert) -> bool:
        return alert.disable_once_fired

    days_or_value.short_description = "Days/Value"
    disable_once_fired_display.short_description = "Disable after fired"
    disable_once_fired_display.admin_order_field = "disable_once_fired"
    list_display = [
        "stock", "name", "type", "days_or_value", "recipient", "enabled", "disable_once_fired_display"
    ]
    list_filter = ["type","stock"]
    search_fields = ["stock__symbol", "stock__name", "name", "notes"]


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
