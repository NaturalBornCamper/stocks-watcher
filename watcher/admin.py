from typing import Union

from django.contrib import admin

from watcher.models import Stock, Price, Alert, QuantStock, Quant, CompiledQuant


class StockAdmin(admin.ModelAdmin):
    def prices_count(self, stock: Stock) -> str:
        return stock.price.count()

    def alerts_count(self, stock: Stock) -> str:
        return stock.alert.count()

    def dividend_yield_display(self, stock: Stock) -> str:
        return f"{stock.dividend_yield}%"

    prices_count.short_description = "Prices count"
    alerts_count.short_description = "Alerts count"
    list_display = ["symbol", "name", "market", "currency", "dividend_yield_display", "prices_count", "alerts_count"]


class PriceAdmin(admin.ModelAdmin):
    list_display = ["stock", "date", "open", "low", "high", "close"]
    list_filter = ["stock"]


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
    list_display = [
        "stock", "name", "type", "days_or_value", "recipient", "enabled", "disable_once_fired_display"
    ]
    list_filter = ["stock"]


admin.site.register(Stock, StockAdmin)
admin.site.register(Price, PriceAdmin)
admin.site.register(Alert, AlertAdmin)
admin.site.register(QuantStock)
admin.site.register(Quant)
admin.site.register(CompiledQuant)
