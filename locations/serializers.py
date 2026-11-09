from rest_framework import serializers

from .models import Category, Location, Review, ReviewVote


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name", "description", "created_at")
        read_only_fields = ("id", "created_at")


class LocationSerializer(serializers.ModelSerializer):
    author = serializers.ReadOnlyField(source="author.username")
    category_name = serializers.ReadOnlyField(source="category.name")

    # Calculated in ORM (see selectors.py)
    avg_rating = serializers.FloatField(read_only=True)
    reviews_count = serializers.IntegerField(read_only=True)
    views_7d = serializers.IntegerField(read_only=True)
    popularity = serializers.FloatField(read_only=True)

    class Meta:
        model = Location
        fields = (
            "id", "title", "description", "category", "category_name",
            "address", "latitude", "longitude", "author",
            "avg_rating", "reviews_count", "views_7d", "popularity",
            "created_at", "updated_at",
        )
        read_only_fields = ("id", "author", "created_at", "updated_at")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for key in ("avg_rating", "popularity"):
            if data.get(key) is not None:
                data[key] = round(data[key], 2)
        return data


class ReviewSerializer(serializers.ModelSerializer):
    author = serializers.ReadOnlyField(source="author.username")
    likes_count = serializers.IntegerField(read_only=True)
    dislikes_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Review
        fields = (
            "id",
            "location",
            "author",
            "rating",
            "comment",
            "likes_count",
            "dislikes_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "location", "author", "created_at", "updated_at")


class VoteSerializer(serializers.Serializer):
    vote = serializers.ChoiceField(choices=["like", "dislike"])

    def validate_vote(self, value):
        return ReviewVote.Value.LIKE if value == "like" else ReviewVote.Value.DISLIKE