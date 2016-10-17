import json

from django.db import models


class DataStore(models.Model):
    key = models.CharField(max_length=32)
    data = models.TextField()

    def as_dict(self):
        return json.loads(self.data)
