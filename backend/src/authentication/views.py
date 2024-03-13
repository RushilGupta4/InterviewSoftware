# webapp/auth/views.py

from datetime import datetime

from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from google.oauth2 import id_token
from google.auth.transport import requests

User = get_user_model()


class PasswordLoginView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response({"detail": "Email and password are required."}, status=400)

        try:
            user = User.objects.get(email=email)
        except:
            return Response({"detail": "Invalid email or password."}, status=400)

        if not user.check_password(password):
            return Response({"detail": "Invalid email or password."}, status=400)

        refresh = RefreshToken.for_user(user)  # Generate JWT token for user
        response = Response({"detail": "Success"})

        response.set_cookie(
            key="refresh_token",
            value=str(refresh),
            httponly=True,
            samesite=settings.SAMESITE,
            secure=settings.HTTPS_SECURE,
            expires=datetime.utcnow() + refresh.lifetime,
        )
        response.set_cookie(
            key="access_token",
            value=str(refresh.access_token),
            httponly=True,
            samesite=settings.SAMESITE,
            secure=settings.HTTPS_SECURE,
            expires=datetime.utcnow() + refresh.access_token.lifetime,
        )

        return response


class GoogleLoginView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        token = request.data.get("token")
        try:
            idinfo = id_token.verify_oauth2_token(
                token, requests.Request(), settings.GOOGLE_OAUTH2_CLIENT_ID
            )

            try:
                user = User.objects.get(email=idinfo["email"])
                if not user.google_login:
                    return Response(
                        {"detail": "Google login not allowed for this user."}, status=403
                    )
            except User.DoesNotExist:
                user = User.objects.create(
                    email=idinfo["email"], google_login=True, password_login=False
                )

            refresh = RefreshToken.for_user(user)  # Generate JWT token for user
            response = Response({"detail": "Success"})

            response.set_cookie(
                key="refresh_token",
                value=str(refresh),
                httponly=True,
                samesite=settings.SAMESITE,
                secure=settings.HTTPS_SECURE,
                expires=datetime.utcnow() + settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"],
            )
            response.set_cookie(
                key="access_token",
                value=str(refresh.access_token),
                httponly=True,
                samesite=settings.SAMESITE,
                secure=settings.HTTPS_SECURE,
                expires=datetime.utcnow() + settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"],
            )

            return response

        except ValueError:
            return Response({"detail": "Invalid token"}, status=400)


class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh = request.COOKIES.get("refresh_token", None)
        if not refresh:
            return Response({"detail": "No refresh token provided."}, status=400)

        request.data["refresh"] = refresh
        try:
            response = super().post(request, *args, **kwargs)

            # Set the new access and refresh tokens in httpOnly cookies
            response.set_cookie(
                key="access_token",
                value=response.data["access"],
                httponly=True,
                samesite=settings.SAMESITE,
                secure=settings.HTTPS_SECURE,
                expires=settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"],
            )
            response.set_cookie(
                key="refresh_token",
                value=response.data["refresh"],
                httponly=True,
                samesite=settings.SAMESITE,
                secure=settings.HTTPS_SECURE,
                expires=settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"],
            )
            return response
        except (TokenError, InvalidToken) as e:
            return Response({"detail": str(e)}, status=400)


class CustomTokenVerifyView(TokenVerifyView):
    def post(self, request, *args, **kwargs):
        access = request.COOKIES.get("access_token", None)
        if not access:
            return Response({"detail": "No access token provided."}, status=400)

        request.data["token"] = access
        try:
            return super().post(request, *args, **kwargs)
        except (TokenError, InvalidToken) as e:
            return Response({"detail": str(e)}, status=400)


class LogoutView(APIView):
    def post(self, request):
        response = Response({"detail": "Success"})

        refresh_token = request.COOKIES.get("refresh_token")
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass

        response.delete_cookie("refresh_token")
        response.delete_cookie("access_token")

        return response
