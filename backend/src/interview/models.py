import uuid
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


# Create your models here.
class Interview(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    sid = models.CharField(max_length=100)
    uid = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)

    company_name = models.CharField(max_length=100)
    job_description = models.TextField()

    feedback = models.TextField(null=True)
    transcript = models.TextField(null=True)

    started = models.BooleanField(default=False)
    completed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["user", "uid"]

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} - {self.created_at.date()}"
