from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.management.utils import get_random_secret_key
from .managers import UserManager


class User(AbstractUser):
    # Assuming 'username' field is removed or not used
    username = None
    email = models.EmailField(_("email address"), unique=True, db_index=True)
    secret_key = models.CharField(max_length=255, default=get_random_secret_key)

    first_name = models.CharField(_("first name"), max_length=30, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)

    google_login = models.BooleanField(default=False)
    password_login = models.BooleanField(default=False)

    is_admin = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")

    def regenerate_secret_key(self):
        self.secret_key = get_random_secret_key()
        self.save()

    def __str__(self):
        return self.email
