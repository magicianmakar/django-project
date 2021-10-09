from django.contrib.auth.models import User
from django.db import models


class AliexpressAccount(models.Model):
    user = models.ForeignKey(User, related_name='aliexpress_account', on_delete=models.CASCADE)

    access_token = models.TextField(default='')
    aliexpress_user_id = models.CharField(max_length=255, default='', blank=True)
    aliexpress_username = models.CharField(max_length=255, default='', blank=True)

    data = models.TextField(default='', blank=True)

    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.aliexpress_user_id} ({self.aliexpress_username})"
