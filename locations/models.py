from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class LocationQuerySet(models.QuerySet):
    def delete(self):
        """Mass deletion is also soft delete."""
        return self.update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class LocationManager(models.Manager):
    """Default manager: returns only non-deleted locations."""

    def get_queryset(self):
        return LocationQuerySet(self.model, using=self._db).filter(is_deleted=False)


class Location(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="locations"
    )
    address = models.CharField(max_length=500)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("-90")), MaxValueValidator(Decimal("90"))],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("-180")), MaxValueValidator(Decimal("180"))],
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="locations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Soft delete
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = LocationManager()          # live only
    all_objects = models.Manager()       # all, including deleted

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_deleted", "-created_at"]),
        ]

    def __str__(self):
        return self.title

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)


class Review(models.Model):
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="reviews"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["location", "author"], name="unique_review_per_user_location"
            ),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="review_rating_between_1_and_5",
            ),
        ]

    def __str__(self):
        return f"{self.author} → {self.location} ({self.rating})"


class ReviewVote(models.Model):
    class Value(models.IntegerChoices):
        LIKE = 1, "Like"
        DISLIKE = -1, "Dislike"

    review = models.ForeignKey(
        Review, on_delete=models.CASCADE, related_name="votes"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_votes"
    )
    value = models.SmallIntegerField(choices=Value.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["review", "user"], name="unique_vote_per_user_review"
            ),
        ]

    def __str__(self):
        return f"{self.user} {self.get_value_display()} review#{self.review_id}"


class LocationView(models.Model):
    """A single recorded view (after checking the limit in Redis)."""

    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="views"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="location_views",
    )
    viewed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["location", "viewed_at"]),
        ]

class LocationSubscription(models.Model):
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="subscriptions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="location_subscriptions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["location", "user"], name="unique_subscription_per_user_location"
            ),
        ]

    def __str__(self):
        return f"{self.user} → {self.location}"