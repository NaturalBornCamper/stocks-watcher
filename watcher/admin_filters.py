from django.contrib.admin import SimpleListFilter

from quant.models import SARating


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
