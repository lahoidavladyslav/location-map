from django.contrib import admin

from .models import Category, Location, LocationView, Review, ReviewVote


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "author", "is_deleted", "created_at")
    list_filter = ("is_deleted", "category")
    search_fields = ("title", "description", "address")

    def get_queryset(self, request):
        # В адмінці бачимо і видалені локації
        return Location.all_objects.all()


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("location", "author", "rating", "created_at")
    list_filter = ("rating",)


admin.site.register(ReviewVote)
admin.site.register(LocationView)