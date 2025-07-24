from django.contrib import admin
from django.db.models import Count, Q

from apps.transaction_adjuster.models import StockTransaction


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
