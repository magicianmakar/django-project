from django.db import models
from django.contrib.auth.models import User


class HubspotAccount(models.Model):
    hubspot_user = models.OneToOneField(User, on_delete=models.CASCADE)
    hubspot_vid = models.IntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.hubspot_vid} {self.hubspot_user.email}'
