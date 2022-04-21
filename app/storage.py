from django.core.files.storage import get_storage_class
from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings


class CachedS3BotoStorage(S3Boto3Storage):
    """
    S3 storage backend that saves the files locally, too.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.location = settings.STATICFILES_LOCATION
        self.local_storage = get_storage_class(
            "compressor.storage.CompressorFileStorage")()

    def save(self, name, content, max_length=None):
        non_gzipped_file_content = content.file
        name = super().save(name, content, max_length)
        content.file = non_gzipped_file_content
        self.local_storage._save(name, content)
        return name


# We need a custom Storage Class for our Media files because we
# want to have separate locations for Static and Media files.
class CachedMediaS3BotoStorage(S3Boto3Storage):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.location = settings.MEDIAFILES_LOCATION
