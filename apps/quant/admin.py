from django.contrib import admin

from apps.quant.models import SAStock, SARating, CompiledSAScore, CompiledSAScoreDecayed
from apps.quant.admin_filters import DateListFilter


class SAStockAdmin(admin.ModelAdmin):
    list_display = ["symbol", "name", "stock"]
    search_fields = ["symbol", "name"]


class SARatingAdmin(admin.ModelAdmin):
    list_display = [
        "sa_stock__symbol", "sa_stock__name", "rank", "quant",
        "rating_seeking_alpha", "rating_wall_street", "type", "date"
    ]
    list_filter = ["type", DateListFilter]
    search_fields = ["sa_stock__symbol", "sa_stock__name", "type"]


class CompiledSAScoreAdmin(admin.ModelAdmin):
    list_display = ["sa_stock__symbol", "sa_stock__name", "score", "count", "type", "latest_quant_date"]
    list_filter = ["type"]
    search_fields = ["sa_stock__symbol", "sa_stock__name", "type"]


admin.site.register(SAStock, SAStockAdmin)
admin.site.register(SARating, SARatingAdmin)
admin.site.register(CompiledSAScore, CompiledSAScoreAdmin)
admin.site.register(CompiledSAScoreDecayed, CompiledSAScoreAdmin)
