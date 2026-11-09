import hashlib

from django.core.cache import cache

VERSION_KEY = "locations:list:version"
LIST_TTL = 60 * 5  # 5 minutes


def _get_version() -> int:
    version = cache.get(VERSION_KEY)
    if version is None:
        cache.add(VERSION_KEY, 1, timeout=None)
        version = cache.get(VERSION_KEY) or 1
    return version


def build_list_key(query_params) -> str:
    """The key depends on the version and all query parameters (filters, page, sorting)."""
    items = sorted(query_params.lists())
    digest = hashlib.md5(repr(items).encode()).hexdigest()
    return f"locations:list:v{_get_version()}:{digest}"


def invalidate_locations_list() -> None:
    """Increments the version: all cached lists immediately become outdated."""
    try:
        cache.incr(VERSION_KEY)
    except ValueError:  # key does not exist yet
        cache.set(VERSION_KEY, 2, timeout=None)