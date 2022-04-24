from django.core.files.storage import get_storage_class
from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings


class CachedS3BotoStorage(S3Boto3Storage):
    """
    S3 storage backend that saves the files locally, too.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.local_storage = get_storage_class(
            "compressor.storage.CompressorFileStorage")()

    def save(self, name, content):
        self.local_storage._save(name, content)
        super().save(name, self.local_storage._open(name))
        return name


# We need a custom Storage Class for our Media files because we
# want to have separate locations for Static and Media files.
class CachedMediaS3BotoStorage(S3Boto3Storage):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.location = settings.MEDIAFILES_LOCATION
