from django.core.cache import cache
from django.db import IntegrityError
from django.db.models import F, ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import generics, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from . import exports
from .cache import LIST_TTL, build_list_key
from .filters import LocationFilter
from .models import Category, Location, LocationSubscription, ReviewVote
from .permissions import IsAdminOrReadOnly, IsOwnerOrAdmin
from .selectors import locations_queryset, reviews_queryset
from .serializers import (
    CategorySerializer,
    LocationSerializer,
    ReviewSerializer,
    VoteSerializer,
)
from .services import register_view

VoteCountsSerializer = inline_serializer(
    name="VoteCounts",
    fields={
        "likes_count": serializers.IntegerField(),
        "dislikes_count": serializers.IntegerField(),
    },
)

SubscribedSerializer = inline_serializer(
    name="Subscribed", fields={"subscribed": serializers.BooleanField()}
)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Data conflict."
    default_code = "conflict"


class ReviewAlreadyExists(Conflict):
    default_detail = "You have already left a review for this location."
    default_code = "review_already_exists"


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            raise Conflict("Cannot delete a category that contains locations.")


class LocationViewSet(viewsets.ModelViewSet):
    serializer_class = LocationSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsOwnerOrAdmin]
    filterset_class = LocationFilter
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "avg_rating", "popularity"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return locations_queryset()

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        ordering = self.request.query_params.get("ordering", "")
        if ordering.lstrip("-") == "avg_rating":
            field = F("avg_rating")
            queryset = queryset.order_by(
                field.desc(nulls_last=True)
                if ordering.startswith("-")
                else field.asc(nulls_last=True)
            )
        return queryset

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def list(self, request, *args, **kwargs):
        key = build_list_key(request.query_params)
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)

        response = super().list(request, *args, **kwargs)
        if response.status_code == 200:
            cache.set(key, response.data, LIST_TTL)
        return response

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if register_view(instance, request):
            instance = self.get_object()  # re-read so views_7d is up to date
        return Response(self.get_serializer(instance).data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "file_format",
                str,
                enum=["json", "csv"],
                description="File format (default json)",
            )
        ],
        responses={200: OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        file_format = request.query_params.get("file_format", "json").lower()
        if file_format not in ("json", "csv"):
            raise ValidationError({"file_format": "Allowed values: json, csv."})

        queryset = self.filter_queryset(self.get_queryset())
        df = exports.build_dataframe(queryset)

        if file_format == "csv":
            content = "\ufeff" + exports.to_csv(df)
            content_type = "text/csv; charset=utf-8"
        else:
            content = exports.to_json(df)
            content_type = "application/json; charset=utf-8"

        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="locations.{file_format}"'
        return response

    @extend_schema(
        request=None,
        responses={
            200: SubscribedSerializer,
            201: SubscribedSerializer,
            204: OpenApiResponse(description="Subscription cancelled"),
        },
    )
    @action(
        detail=True,
        methods=["post", "delete"],
        url_path="subscribe",
        permission_classes=[IsAuthenticated],
    )
    def subscribe(self, request, pk=None):
        location = get_object_or_404(Location.objects, pk=pk)

        if request.method == "POST":
            _, created = LocationSubscription.objects.get_or_create(
                location=location, user=request.user
            )
            return Response(
                {"subscribed": True},
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )

        LocationSubscription.objects.filter(location=location, user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class LocationReviewListCreateView(generics.ListCreateAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_location(self):
        return get_object_or_404(Location.objects, pk=self.kwargs["location_pk"])

    def get_queryset(self):
        return reviews_queryset().filter(location_id=self.kwargs["location_pk"])

    def perform_create(self, serializer):
        location = self.get_location()
        user = self.request.user
        if location.reviews.filter(author=user).exists():
            raise ReviewAlreadyExists()
        try:
            serializer.save(location=location, author=user)
        except IntegrityError:  # race condition of two concurrent requests
            raise ReviewAlreadyExists()


class ReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsOwnerOrAdmin]

    def get_queryset(self):
        return reviews_queryset()


class ReviewVoteView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_review(self, pk):
        return get_object_or_404(reviews_queryset(), pk=pk)

    def _counts(self, pk):
        review = self._get_review(pk)
        return {"likes_count": review.likes_count, "dislikes_count": review.dislikes_count}

    @extend_schema(
        request=VoteSerializer,
        responses={200: VoteCountsSerializer, 201: VoteCountsSerializer},
    )
    def post(self, request, pk):
        review = self._get_review(pk)
        if review.author_id == request.user.pk:
            raise PermissionDenied("Cannot vote for your own review.")

        serializer = VoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        _, created = ReviewVote.objects.update_or_create(
            review_id=review.pk,
            user=request.user,
            defaults={"value": serializer.validated_data["vote"]},
        )
        return Response(
            self._counts(pk),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(request=None, responses={200: VoteCountsSerializer})
    def delete(self, request, pk):
        self._get_review(pk)
        ReviewVote.objects.filter(review_id=pk, user=request.user).delete()
        return Response(self._counts(pk))