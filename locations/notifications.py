import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import Review

logger = logging.getLogger(__name__)


def notify_new_review(review_id: int) -> None:
    """Emails the location author and subscribers about a new review.
    The review author does not receive an email. Mail error does not break the request."""
    try:
        review = Review.objects.select_related("location__author", "author").get(pk=review_id)
    except Review.DoesNotExist:
        return

    location = review.location
    recipients = {location.author_id: location.author}
    for sub in location.subscriptions.select_related("user"):
        recipients.setdefault(sub.user_id, sub.user)
    recipients.pop(review.author_id, None)

    for user in recipients.values():
        if not user.email:
            continue
        if user.pk == location.author_id:
            intro = f"A new review has been added to your location «{location.title}»."
        else:
            intro = f"There is a new review for «{location.title}», which you are subscribed to."
        try:
            send_mail(
                subject=f"New Review: {location.title}",
                message=(
                    f"{intro}\n\n"
                    f"Author: {review.author.username}\n"
                    f"Rating: {review.rating}/5\n"
                    f"Comment: {review.comment}\n"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
            )
        except Exception:
            logger.exception("Failed to send email to user %s", user.pk)