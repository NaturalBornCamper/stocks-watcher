import re

from django.contrib import admin
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe
from django.db.models import Count, Q

from apps.transaction_adjuster.models import StockTransaction, StockSplit


class DuplicateTransactionFilter(admin.SimpleListFilter):
    title = 'Duplicate Transactions'
    parameter_name = 'duplicate'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Show Duplicates'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            # Find transactions with the same symbol, date, and quantity
            duplicates = StockTransaction.objects.values('symbol', 'date', 'quantity') \
                .annotate(count=Count('id')) \
                .filter(count__gt=1)

            if duplicates:
                q_objects = Q()
                for duplicate in duplicates:
                    q_objects |= Q(
                        symbol=duplicate['symbol'],
                        date=duplicate['date'],
                        quantity=duplicate['quantity']
                    )
                return queryset.filter(q_objects)
            return queryset.none()
        return queryset


class StockTransactionAdmin(admin.ModelAdmin):
    def notes_hint(self, stock_transaction: StockTransaction) -> str:
        if stock_transaction.notes:
            # Replace newlines with <br> and add links
            notes = stock_transaction.notes.replace("\n", "<br>")
            notes = re.sub(r"(https?://\S+)", rf"<a href=\"\1\" target=\"{StockTransaction.pk}\">\1</a>", notes)
            return render_to_string("admin/notes.html", context={"notes": mark_safe(notes)})
        else:
            return ""

    # Columns to display
    list_display = ["date", "symbol", "notes_hint", "quantity", "adjusted_quantity", "price_per_share", "adjusted_price_per_share",
                    "total_cost", "currency"]

    # Fields to search for "All words" (Default search behavior)
    search_fields = ["date", "symbol", "notes"]

    # Side filters
    list_filter = ["symbol", "currency", "type", DuplicateTransactionFilter]

    # Custom descriptions for columns
    notes_hint.short_description = "Notes"

    # Model fields to use for custom columns ordering
    notes_hint.admin_order_field = "notes"


class StockSplitAdmin(admin.ModelAdmin):
    def notes_hint(self, stock_split: StockSplit) -> str:
        if stock_split.notes:
            # Replace newlines with <br> and add links
            notes = stock_split.notes.replace("\n", "<br>")
            notes = re.sub(r"(https?://\S+)", rf"<a href=\"\1\" target=\"{StockSplit.pk}\">\1</a>", notes)
            return render_to_string("admin/notes.html", context={"notes": mark_safe(notes)})
        else:
            return ""

    # Columns to display
    list_display = ["date", "symbol", "notes_hint", "split"]

    # Fields to search for "All words" (Default search behavior)
    search_fields = ["date", "symbol", "split", "notes"]

    # Side filters
    list_filter = ["symbol", "split"]

    # Custom descriptions for columns
    notes_hint.short_description = "Notes"

    # Model fields to use for custom columns ordering
    notes_hint.admin_order_field = "notes"


admin.site.register(StockTransaction, StockTransactionAdmin)
admin.site.register(StockSplit, StockSplitAdmin)