import mimetypes

from django.conf import settings
from django.utils.crypto import get_random_string

from leadgalaxy.utils import aws_s3_upload


def upload_report_to_aws(obj, bucket_name):
    path = f'uploads/{bucket_name}'

    ext = obj.name.rsplit('.')[-1]
    # Randomize filename in order to not overwrite an existing file
    random_name = get_random_string(length=10)

    object_name = f'{path}/{random_name}.{ext}'
    mimetype = mimetypes.guess_type(obj.name)[0]

    return aws_s3_upload(
        filename=object_name,
        fp=obj,
        mimetype=mimetype,
        bucket_name=settings.S3_UPLOADS_BUCKET
    )
