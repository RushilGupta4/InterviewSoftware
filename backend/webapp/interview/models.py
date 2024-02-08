from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


# Create your models here.
class Interview(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    sid = models.CharField(max_length=100, unique=True)
    uid = models.CharField(max_length=100)

    job_description = models.ForeignKey("JobDescription", on_delete=models.CASCADE)
    feedback = models.TextField()
    transcript = models.TextField()
    confidence = models.IntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["user", "uid"]

    def __str__(self):
        return (
            f"{self.user.first_name} {self.user.last_name} - {self.created_at.date()}"
        )
