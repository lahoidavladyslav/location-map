from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase
from django.core import mail

from locations.models import Category, Location, Review

User = get_user_model()


class BaseAPITestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("alice", "alice@example.com", "StrongPass12345")
        self.other = User.objects.create_user("bob", "bob@example.com", "StrongPass12345")
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "StrongPass12345")
        self.category = Category.objects.create(name="Парки")

    def make_location(self, author=None, **kwargs):
        data = dict(
            title="Парк",
            description="Гарне місце",
            category=self.category,
            address="Київ",
            latitude=50.44,
            longitude=30.51,
            author=author or self.user,
        )
        data.update(kwargs)
        return Location.objects.create(**data)

    @property
    def location_payload(self):
        return {
            "title": "Новий парк",
            "description": "Опис",
            "category": self.category.pk,
            "address": "Львів",
            "latitude": "49.839700",
            "longitude": "24.029700",
        }


class AuthTests(BaseAPITestCase):
    def test_register_login_logout(self):
        r = self.client.post(
            "/api/auth/register/",
            {"username": "newbie", "email": "n@example.com", "password": "StrongPass12345"},
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

        r = self.client.post(
            "/api/auth/login/",
            {"username": "newbie", "password": "StrongPass12345"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)

    def test_login_wrong_password(self):
        r = self.client.post(
            "/api/auth/login/", {"username": "alice", "password": "wrong"}, format="json"
        )
        self.assertEqual(r.status_code, 400)


class LocationPermissionTests(BaseAPITestCase):
    def test_anonymous_can_read_but_not_create(self):
        self.make_location()
        self.assertEqual(self.client.get("/api/locations/").status_code, 200)
        r = self.client.post("/api/locations/", self.location_payload, format="json")
        self.assertIn(r.status_code, (401, 403))

    def test_authenticated_can_create(self):
        self.client.force_authenticate(self.user)
        r = self.client.post("/api/locations/", self.location_payload, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["author"], "alice")

    def test_only_owner_or_admin_can_edit(self):
        loc = self.make_location(author=self.user)
        url = f"/api/locations/{loc.pk}/"

        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.patch(url, {"title": "X"}, format="json").status_code, 403)

        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.patch(url, {"title": "X"}, format="json").status_code, 200)

        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.patch(url, {"title": "Y"}, format="json").status_code, 200)

    def test_invalid_coordinates(self):
        self.client.force_authenticate(self.user)
        payload = {**self.location_payload, "latitude": "95.000000"}
        r = self.client.post("/api/locations/", payload, format="json")
        self.assertEqual(r.status_code, 400)


class SoftDeleteTests(BaseAPITestCase):
    def test_delete_is_soft(self):
        loc = self.make_location()
        self.client.force_authenticate(self.user)
        r = self.client.delete(f"/api/locations/{loc.pk}/")
        self.assertEqual(r.status_code, 204)

        self.assertEqual(self.client.get(f"/api/locations/{loc.pk}/").status_code, 404)
        self.assertFalse(Location.objects.filter(pk=loc.pk).exists())
        self.assertTrue(Location.all_objects.filter(pk=loc.pk, is_deleted=True).exists())


class ReviewTests(BaseAPITestCase):
    def test_create_review_and_duplicate_conflict(self):
        loc = self.make_location()
        self.client.force_authenticate(self.other)
        url = f"/api/locations/{loc.pk}/reviews/"

        r = self.client.post(url, {"rating": 5, "comment": "Супер"}, format="json")
        self.assertEqual(r.status_code, 201)

        r = self.client.post(url, {"rating": 4, "comment": "Ще раз"}, format="json")
        self.assertEqual(r.status_code, 409)

    def test_rating_out_of_range(self):
        loc = self.make_location()
        self.client.force_authenticate(self.other)
        url = f"/api/locations/{loc.pk}/reviews/"
        for bad in (0, 6):
            r = self.client.post(url, {"rating": bad, "comment": "x"}, format="json")
            self.assertEqual(r.status_code, 400)

    def test_anonymous_cannot_review(self):
        loc = self.make_location()
        r = self.client.post(
            f"/api/locations/{loc.pk}/reviews/", {"rating": 5, "comment": "x"}, format="json"
        )
        self.assertIn(r.status_code, (401, 403))


class VoteTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.loc = self.make_location()
        self.review = Review.objects.create(
            location=self.loc, author=self.user, rating=5, comment="ok"
        )
        self.url = f"/api/reviews/{self.review.pk}/vote/"

    def test_like_then_change_to_dislike(self):
        self.client.force_authenticate(self.other)
        r = self.client.post(self.url, {"vote": "like"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data, {"likes_count": 1, "dislikes_count": 0})

        r = self.client.post(self.url, {"vote": "dislike"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, {"likes_count": 0, "dislikes_count": 1})

    def test_cannot_vote_own_review(self):
        self.client.force_authenticate(self.user)
        r = self.client.post(self.url, {"vote": "like"}, format="json")
        self.assertEqual(r.status_code, 403)


class RatingPopularityViewsTests(BaseAPITestCase):
    def test_rating_and_popularity_computed(self):
        loc = self.make_location()
        Review.objects.create(location=loc, author=self.other, rating=4, comment="a")
        Review.objects.create(location=loc, author=self.admin, rating=2, comment="b")

        r = self.client.get(f"/api/locations/{loc.pk}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["avg_rating"], 3.0)
        self.assertEqual(r.data["reviews_count"], 2)
        self.assertEqual(r.data["views_7d"], 1)
        # 3.0*10 + 2*3 + 1*1
        self.assertEqual(r.data["popularity"], 37.0)

    def test_view_counted_once_per_hour(self):
        loc = self.make_location()
        self.client.force_authenticate(self.other)
        for _ in range(3):
            r = self.client.get(f"/api/locations/{loc.pk}/")
        self.assertEqual(r.data["views_7d"], 1)


class ListFilterTests(BaseAPITestCase):
    def test_search_filter_and_ordering(self):
        other_cat = Category.objects.create(name="Музеї")
        a = self.make_location(title="Центральний парк")
        b = self.make_location(title="Історичний музей", category=other_cat, author=self.other)
        Review.objects.create(location=b, author=self.user, rating=5, comment="ok")

        r = self.client.get("/api/locations/?search=парк")
        self.assertEqual([x["id"] for x in r.data["results"]], [a.pk])

        r = self.client.get(f"/api/locations/?category={other_cat.pk}")
        self.assertEqual([x["id"] for x in r.data["results"]], [b.pk])

        r = self.client.get(f"/api/locations/?author={self.other.pk}")
        self.assertEqual([x["id"] for x in r.data["results"]], [b.pk])

        r = self.client.get("/api/locations/?min_rating=4")
        self.assertEqual([x["id"] for x in r.data["results"]], [b.pk])

        r = self.client.get("/api/locations/?ordering=-avg_rating")
        self.assertEqual([x["id"] for x in r.data["results"]], [b.pk, a.pk])

    def test_pagination(self):
        for i in range(12):
            self.make_location(title=f"Локація {i}")
        r = self.client.get("/api/locations/")
        self.assertEqual(r.data["count"], 12)
        self.assertEqual(len(r.data["results"]), 10)


class CacheInvalidationTests(BaseAPITestCase):
    def test_list_cache_refreshes_after_changes(self):
        self.make_location()
        self.assertEqual(self.client.get("/api/locations/").data["count"], 1)

        # transaction.on_commit у тестах не спрацьовує без цього контексту
        with self.captureOnCommitCallbacks(execute=True):
            self.make_location(title="Друга")
        self.assertEqual(self.client.get("/api/locations/").data["count"], 2)

        loc = Location.objects.first()
        with self.captureOnCommitCallbacks(execute=True):
            Review.objects.create(location=loc, author=self.other, rating=5, comment="ok")
        results = self.client.get("/api/locations/").data["results"]
        self.assertTrue(any(x["reviews_count"] == 1 for x in results))


class ExportTests(BaseAPITestCase):
    def test_export_json_and_csv(self):
        self.make_location()
        r = self.client.get("/api/locations/export/?file_format=json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r["Content-Disposition"])

        r = self.client.get("/api/locations/export/?file_format=csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r["Content-Type"])
        self.assertIn("title", r.content.decode("utf-8-sig").splitlines()[0])

    def test_export_invalid_format(self):
        r = self.client.get("/api/locations/export/?file_format=xml")
        self.assertEqual(r.status_code, 400)

class NotificationTests(BaseAPITestCase):
    def test_subscribe_unsubscribe(self):
        loc = self.make_location()
        url = f"/api/locations/{loc.pk}/subscribe/"
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(url).status_code, 201)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 204)

    def test_anonymous_cannot_subscribe(self):
        loc = self.make_location()
        r = self.client.post(f"/api/locations/{loc.pk}/subscribe/")
        self.assertIn(r.status_code, (401, 403))

    def test_author_and_subscribers_get_email(self):
        loc = self.make_location(author=self.user)  # alice
        self.client.force_authenticate(self.other)  # bob підписується
        self.client.post(f"/api/locations/{loc.pk}/subscribe/")

        self.client.force_authenticate(self.admin)  # admin пише відгук
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(
                f"/api/locations/{loc.pk}/reviews/",
                {"rating": 5, "comment": "Клас"},
                format="json",
            )
        self.assertEqual(r.status_code, 201)

        recipients = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(recipients, ["alice@example.com", "bob@example.com"])