import django_filters

from .models import Location


class LocationFilter(django_filters.FilterSet):
    category = django_filters.NumberFilter(field_name="category_id")
    author = django_filters.NumberFilter(field_name="author_id")
    author_username = django_filters.CharFilter(
        field_name="author__username", lookup_expr="iexact"
    )
    min_rating = django_filters.NumberFilter(field_name="avg_rating", lookup_expr="gte")
    max_rating = django_filters.NumberFilter(field_name="avg_rating", lookup_expr="lte")

    class Meta:
        model = Location
        fields = ["category", "author", "author_username", "min_rating", "max_rating"]