from django.core.cache import cache

from .models import Location, LocationView

VIEW_TTL_SECONDS = 60 * 60  # one view per hour


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _viewer_id(request) -> str:
    if request.user.is_authenticated:
        return f"user:{request.user.pk}"
    return f"ip:{_client_ip(request)}"


def register_view(location: Location, request) -> bool:
    """Registers a view if this viewer has not viewed the location within the hour.
    Returns True if the view is successfully registered."""
    key = f"loc_view:{location.pk}:{_viewer_id(request)}"

    # cache.add is atomic (SET NX in Redis): the key will be created only if it does not exist yet,
    # so during a race condition, the view will be counted only once.
    if not cache.add(key, 1, timeout=VIEW_TTL_SECONDS):
        return False

    LocationView.objects.create(
        location=location,
        user=request.user if request.user.is_authenticated else None,
    )
    return True