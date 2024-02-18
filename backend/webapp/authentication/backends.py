# authentication/backends.py

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        # Access the access token directly from the cookies
        raw_token = request.COOKIES.get("access_token") or None
        if raw_token is None:
            return None

        # Validate the token
        try:
            validated_token = self.get_validated_token(raw_token)
        except InvalidToken as exc:
            raise AuthenticationFailed("Invalid token") from exc

        # Get the user associated with this token
        return self.get_user(validated_token), validated_token

    def authenticate_header(self, request):
        return "Bearer"
