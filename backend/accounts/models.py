from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_ADMIN = "admin"
    ROLE_WORKER = "worker"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "管理员"),
        (ROLE_WORKER, "操作工"),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_WORKER)

    def __str__(self):
        return f"{self.username} ({self.role})"
