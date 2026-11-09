from django.contrib.auth import login, logout
from django.middleware.csrf import get_token
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .serializers import (
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .services import send_password_reset_email

DetailSerializer = inline_serializer(
    name="Detail", fields={"detail": serializers.CharField()}
)


class AuthThrottledView(APIView):
    """Base class for public auth endpoints: sessionless and rate-limited."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class CsrfView(APIView):
    """Sets the csrftoken cookie for subsequent POST/PUT/DELETE requests."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        responses=inline_serializer(
            name="CsrfToken", fields={"csrfToken": serializers.CharField()}
        )
    )
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class RegisterView(AuthThrottledView):
    @extend_schema(request=RegisterSerializer, responses={201: UserSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(AuthThrottledView):
    @extend_schema(request=LoginSerializer, responses={200: UserSerializer})
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: OpenApiResponse(description="Logout successful")})
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class PasswordResetRequestView(AuthThrottledView):
    @extend_schema(request=PasswordResetRequestSerializer, responses={200: DetailSerializer})
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        send_password_reset_email(serializer.validated_data["email"])
        return Response(
            {"detail": "If such an email exists, we have sent instructions."}
        )


class PasswordResetConfirmView(AuthThrottledView):
    @extend_schema(request=PasswordResetConfirmSerializer, responses={200: DetailSerializer})
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password successfully changed."})