import django_filters

from .models import Reading, Debt

class ReadingFilter(django_filters.FilterSet):

    year = django_filters.NumberFilter(
        field_name='period',
        lookup_expr='year'
    )

    month = django_filters.NumberFilter(
        field_name='period',
        lookup_expr='month'
    )

    class Meta:
        model = Reading
        fields = ['customer', 'paid', 'year', 'month']


class DebtFilter(django_filters.FilterSet):

    year = django_filters.NumberFilter(
        field_name='period',
        lookup_expr='year'
    )

    month = django_filters.NumberFilter(
        field_name='period',
        lookup_expr='month'
    )

    class Meta:
        model = Debt
        fields = [
            'customer',
            'paid',
            'is_refinanced',
            'year',
            'month',
            'customer__codigo'
        ]