from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("categories", views.CategoryViewSet, basename="category")
router.register("locations", views.LocationViewSet, basename="location")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "locations/<int:location_pk>/reviews/",
        views.LocationReviewListCreateView.as_view(),
        name="location-reviews",
    ),
    path("reviews/<int:pk>/", views.ReviewDetailView.as_view(), name="review-detail"),
    path("reviews/<int:pk>/vote/", views.ReviewVoteView.as_view(), name="review-vote"),
]