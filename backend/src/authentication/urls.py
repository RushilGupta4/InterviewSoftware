from django.urls import path
from .views import (
    PasswordLoginView,
    GoogleLoginView,
    LogoutView,
    CustomTokenRefreshView,
    CustomTokenVerifyView,
)

urlpatterns = [
    path("login/password/", PasswordLoginView.as_view(), name="password_login"),
    path("login/google/", GoogleLoginView.as_view(), name="google_login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", CustomTokenVerifyView.as_view(), name="token_verify"),
]
