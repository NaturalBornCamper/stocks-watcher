import re
from datetime import datetime

from django import forms
from django.contrib import admin
from django.db import models
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from apps.transaction_adjuster.admin_filters import CustomFiltersGroup, TransactionYearFilter
from apps.transaction_adjuster.models import StockTransaction, StockSplit
from utils.helpers import get_currency_symbol


def format_price(value: float):
    if value is None:
        return None

    # Format number with commas for thousands
    integer_part, decimal_part = f"{value:.10f}".split('.')
    formatted_integer = f"{int(integer_part):,}"

    # Remove trailing zeros but keep at least 2
    decimal_part = decimal_part.rstrip('0')
    if len(decimal_part) < 2:
        decimal_part += '0' * (2 - len(decimal_part))

    return f"{formatted_integer}.{decimal_part}"


class FrenchAwareDateField(forms.DateField):
    """
    Date field that recognizes French date formats (DD/MM/YYYY or DD/MM/YY),
    and falls back to Django's standard date parsing for other formats.
    """

    def to_python(self, value):
        if value in self.empty_values:
            return None

        if not isinstance(value, str):
            return super().to_python(value)

        # Check for French date patterns
        # Pattern 1: DD/MM/YYYY
        pattern1 = r'^\d{2}/\d{2}/\d{4}$'
        # Pattern 2: DD/MM/YY where MM <= 12
        pattern2 = r'^\d{2}/\d{2}/\d{2}$'

        #Remove all empty white spaces from value and renames it
        value_without_spaces = value.replace(" ", "")

        if re.match(pattern1, value_without_spaces):
            # Handle DD/MM/YYYY
            try:
                day, month, year = value_without_spaces.split('/')
                # Convert to Django date format (YYYY-MM-DD)
                date_obj = datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d").date()
                return date_obj
            except (ValueError, IndexError):
                # If parsing fails, fall back to Django's parser
                pass

        elif re.match(pattern2, value_without_spaces):
            # Handle DD/MM/YY (if MM <= 12)
            try:
                day, month, year = value_without_spaces.split('/')
                if int(month) <= 12:  # Only treat as French date if month is valid
                    # Assume 20xx for two-digit years
                    full_year = f"20{year}"
                    # Convert to Django date format
                    date_obj = datetime.strptime(f"{full_year}-{month}-{day}", "%Y-%m-%d").date()
                    return date_obj
            except (ValueError, IndexError):
                # If parsing fails, fall back to Django's parser
                pass

        # Fall back to Django's standard date parsing for all other cases
        return super().to_python(value)


class SmartDecimalField(forms.CharField):
    def to_python(self, value):
        if value in self.empty_values:
            return None

        # Handle input format based on presence of comma or period
        if isinstance(value, str):
            # If there's a comma and no period, treat as French format
            if ',' in value and '.' not in value:
                value = value.replace(',', '.')

        try:
            return super().to_python(value)
        except forms.ValidationError:
            raise forms.ValidationError(
                "Please enter a valid number. Use either '.' (English) or ',' (French) as decimal separator."
            )


class StockTransactionAdminForm(forms.ModelForm):
    # Override date field with a custom field that supports French date formats
    date = FrenchAwareDateField(
        help_text="Accepts both standard dates and French formats (DD/MM/YYYY or DD/MM/YY)"
    )

    # Override decimal fields with a custom field that supports comma as decimal separator
    price_per_share = SmartDecimalField(
        required=False,
        help_text="Use either '.' (English) or ',' (French) as decimal separator"
    )
    total_cost = SmartDecimalField(
        required=False,
        help_text="Use either '.' (English) or ',' (French) as decimal separator"
    )

    class Meta:
        model = StockTransaction
        fields = ["date", "symbol", "currency", "type", "quantity", "price_per_share", "total_cost", "notes"]
        widgets = {
            'currency': forms.RadioSelect(),
            'type': forms.RadioSelect(),
        }


class StockTransactionAdmin(admin.ModelAdmin):
    def formatted_date(self, obj):
        return obj.date.strftime('%Y-%m-%d')

    def notes_hint(self, stock_transaction: StockTransaction) -> str:
        if stock_transaction.notes:
            # Replace newlines with <br> and add links
            notes = stock_transaction.notes.replace("\n", "<br>")
            notes = re.sub(r"(https?://\S+)", rf"<a href=\"\1\" target=\"{StockTransaction.pk}\">\1</a>", notes)
            return render_to_string("admin/notes.html", context={"notes": mark_safe(notes)})
        else:
            return ""

    def formatted_price_per_share(self, obj):
        return f"{format_price(obj.price_per_share)} {get_currency_symbol(obj.currency)}"

    def formatted_adjusted_price_per_share(self, obj):
        return f"{format_price(obj.adjusted_price_per_share)} {get_currency_symbol(obj.currency)}"

    def formatted_total_cost(self, obj):
        return f"{format_price(obj.total_cost)} {get_currency_symbol(obj.currency)}"

    # Makes textareas smaller (For notes)
    formfield_overrides = {
        # For TextField
        models.TextField: {'widget': forms.Textarea(attrs={'rows': 4, 'cols': 120})},
    }

    form = StockTransactionAdminForm

    # Columns to display
    list_display = ["formatted_date", "symbol", "currency", "type", "quantity", "adjusted_quantity",
                    "formatted_price_per_share", "formatted_adjusted_price_per_share",
                    "formatted_total_cost", "notes_hint"]

    # Fields to search for "All words" (Default search behavior)
    search_fields = ["date", "symbol", "notes"]

    # Side filters
    list_filter = ["symbol", "currency", "type", TransactionYearFilter, CustomFiltersGroup]

    # Custom descriptions for columns
    formatted_date.short_description = "Date"
    notes_hint.short_description = "Notes"
    formatted_price_per_share.short_description = "Price Per Share"
    formatted_adjusted_price_per_share.short_description = "Adjusted Price Per Share"
    formatted_total_cost.short_description = "Total Cost"

    # Model fields to use for custom columns ordering
    notes_hint.admin_order_field = "notes"
    formatted_date.admin_order_field = 'date'


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
