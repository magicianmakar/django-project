from django.core.files.storage import get_storage_class
from storages.backends.s3boto import S3BotoStorage
from django.core.files.base import ContentFile
from django.conf import settings


def mainfest_https_fix(content):
    data = content.file.read()
    return ContentFile(data.replace('http://', '//'))


class CachedS3BotoStorage(S3BotoStorage):
    """
    S3 storage backend that saves the files locally, too.
    """
    def __init__(self, *args, **kwargs):
        super(CachedS3BotoStorage, self).__init__(*args, **kwargs)
        self.location = settings.STATICFILES_LOCATION
        self.local_storage = get_storage_class(
            "compressor.storage.CompressorFileStorage")()

    def save(self, name, content):
        if name == '%s/manifest.json' % settings.COMPRESS_OUTPUT_DIR:
            print '\nFix manifest.json'
            content = mainfest_https_fix(content)

        non_gzipped_file_content = content.file
        name = super(CachedS3BotoStorage, self).save(name, content)
        content.file = non_gzipped_file_content
        self.local_storage._save(name, content)
        return name


# We need a custom Storage Class for our Media files because we
# want to have seperate locations for Static and Media files.
class CachedMediaS3BotoStorage(S3BotoStorage):
    def __init__(self, *args, **kwargs):
        super(CachedS3BotoStorage, self).__init__(*args, **kwargs)
        self.location = settings.MEDIAFILES_LOCATION
