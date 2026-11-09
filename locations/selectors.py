from datetime import timedelta

from django.db.models import (
    Avg, Count, ExpressionWrapper, F, FloatField, IntegerField,
    OuterRef, Q, Subquery, Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Location, LocationView, Review, ReviewVote

WEIGHT_RATING = 10
WEIGHT_REVIEWS = 3
WEIGHT_VIEWS = 1
VIEWS_WINDOW_DAYS = 7

def locations_queryset():
    """Locations with calculated rating, reviews count, 7-day views,
    and popularity. Everything is calculated in the DB, nothing is stored."""
    since = timezone.now() - timedelta(days=VIEWS_WINDOW_DAYS)

    # Subquery instead of JOIN on views: this prevents review rows from duplicating
    recent_views = (
        LocationView.objects.filter(location=OuterRef("pk"), viewed_at__gte=since)
        .order_by()
        .values("location")
        .annotate(total=Count("pk"))
        .values("total")
    )

    return (
        Location.objects.select_related("category", "author")
        .annotate(
            avg_rating=Avg("reviews__rating"),
            reviews_count=Count("reviews", distinct=True),
            views_7d=Coalesce(Subquery(recent_views, output_field=IntegerField()), 0),
        )
        .annotate(
            popularity=ExpressionWrapper(
                Coalesce(F("avg_rating"), Value(0.0), output_field=FloatField()) * WEIGHT_RATING
                + F("reviews_count") * WEIGHT_REVIEWS
                + F("views_7d") * WEIGHT_VIEWS,
                output_field=FloatField(),
            )
        )
    )

def reviews_queryset():
    """Reviews with calculated likes/dislikes (in a single query, without N+1)."""
    return (
        Review.objects.select_related("author")
        .filter(location__is_deleted=False)
        .annotate(
            likes_count=Count("votes", filter=Q(votes__value=ReviewVote.Value.LIKE)),
            dislikes_count=Count("votes", filter=Q(votes__value=ReviewVote.Value.DISLIKE)),
        )
        .order_by("-created_at", "-id")
    )