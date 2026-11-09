from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from .notifications import notify_new_review
from .cache import invalidate_locations_list
from .models import Category, Location, Review


@receiver([post_save, post_delete], sender=Location)
@receiver([post_save, post_delete], sender=Review)
@receiver([post_save, post_delete], sender=Category)
def clear_locations_cache(sender, **kwargs):
    # on_commit: clear cache only after a successful transaction commit
    transaction.on_commit(invalidate_locations_list)

@receiver(post_save, sender=Review)
def notify_on_new_review(sender, instance, created, **kwargs):
    if created:
        # after commit, to avoid sending emails about a rolled-back review
        transaction.on_commit(lambda: notify_new_review(instance.pk))