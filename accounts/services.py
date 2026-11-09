from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

User = get_user_model()


def send_password_reset_email(email: str) -> None:
    for user in User.objects.filter(email__iexact=email, is_active=True):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        link = settings.PASSWORD_RESET_URL.format(uid=uid, token=token)

        send_mail(
            subject="Password Reset",
            message=(
                f"Hello, {user.username}!\n\n"
                f"To reset your password, please click the link below:\n{link}\n\n"
                f"uid: {uid}\ntoken: {token}\n\n"
                "If you did not make this request, simply ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )