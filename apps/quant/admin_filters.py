from django.contrib.admin import SimpleListFilter
from django.db.models import Min

from apps.quant.models import SARating


class DateListFilter(SimpleListFilter):
    title = 'date'
    parameter_name = 'date'

    def lookups(self, request, model_admin):
        dates = SARating.objects.order_by("-date").values_list('date', flat=True).distinct()
        return [(date, date) for date in dates]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(date=self.value())
        return queryset


class FirstSeenListFilter(SimpleListFilter):
    """Filter SA stocks by when they first showed up in a ratings dump.
    Picking a date shows stocks first seen on or after it, so the latest date
    means "new this month" and an earlier date means "new since then"."""
    title = "first seen"
    parameter_name = "first_seen"

    def lookups(self, request, model_admin):
        dates = SARating.objects.order_by("-date").values_list("date", flat=True).distinct()
        return [(date, f"On/after {date}") for date in dates]

    def queryset(self, request, queryset):
        if self.value():
            # A stock's "first seen" date is the date of its earliest rating
            return queryset.annotate(first_seen=Min("sarating__date")).filter(first_seen__gte=self.value())
        return queryset
