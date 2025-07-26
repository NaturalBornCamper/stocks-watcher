from django.contrib import admin
from django.db.models import Count, Q

from apps.transaction_adjuster.models import StockTransaction, StockSplit


class CustomFiltersGroup(admin.SimpleListFilter):
    title = 'Custom Filters'
    parameter_name = 'custom_filter'

    def lookups(self, request, model_admin):
        return (
            ('duplicates', 'Show Duplicates'),
            ('no_splits', 'No stock split'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'duplicates':
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
        
        elif self.value() == 'no_splits':
            # Get all symbols that have splits
            split_symbols = StockSplit.objects.values_list('symbol', flat=True).distinct()
            
            # Find transactions with symbols that don't have a corresponding split
            return queryset.exclude(symbol__in=split_symbols)
            
        return queryset


class TransactionYearFilter(admin.SimpleListFilter):
    title = 'Transaction Year'
    parameter_name = 'transaction_year'

    def lookups(self, request, model_admin):
        years = model_admin.model.objects.dates('date', 'year')
        return [(year.year, str(year.year)) for year in years]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(date__year=self.value())
        return queryset
