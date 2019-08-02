from hashlib import sha1
import os

from django.conf import settings

from storages.backends.s3boto import S3BotoStorage
from compressor.storage import CompressorFileStorage


class CachedS3BotoStorage(S3BotoStorage):
    """
    S3 storage backend that saves the files locally, too.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.location = settings.STATICFILES_LOCATION
        self.local_storage = CompressorFileStorage()

    def save(self, name, content):
        name = super().save(name, content)
        self.local_storage._save(name, content)
        return name

    def url(self, name, headers=None, response_headers=None, expire=None):
        base_url = super().url(name, headers=headers, response_headers=response_headers, expire=expire)

        if name.endswith('.js') or name.endswith('.css'):
            the_hash = self.get_hash(name)
            sep = '%' if '?' in base_url else '?'
            base_url = f'{base_url}{sep}{the_hash}'

        return base_url

    def get_hash(self, name):
        git_hash = os.environ.get('HEROKU_SLUG_COMMIT', '')
        return sha1(f'{git_hash}-{name}'.encode()).hexdigest()[:8]


# We need a custom Storage Class for our Media files because we
# want to have seperate locations for Static and Media files.
class CachedMediaS3BotoStorage(S3BotoStorage):
    def __init__(self, *args, **kwargs):
        super(CachedS3BotoStorage, self).__init__(*args, **kwargs)
        self.location = settings.MEDIAFILES_LOCATION
