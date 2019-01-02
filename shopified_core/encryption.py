import hmac
import base64

from Crypto.Cipher import AES
from hashlib import sha256

from django.conf import settings
from leadgalaxy.utils import aws_s3_get_key


def get_new_aes(user, email):
    """ Generate AES instance with an encryption key and nonce """

    key = hmac.new(settings.ENCRYPTION_SECRECT_KEY.encode(),
                   settings.API_SECRECT_KEY.encode(), sha256).digest()

    nonce = hmac.new(settings.ENCRYPTION_SECRECT_KEY.encode(),
                     email.encode(), sha256).digest()[:15]

    key_name = hmac.new(settings.ENCRYPTION_SECRECT_KEY.encode(),
                        '{}.{}'.format(user.id, email.lower()).encode(),
                        sha256).hexdigest()

    return AES.new(key, AES.MODE_CTR, nonce=nonce), key_name


def save_aliexpress_password(user, email, password):
    """ Encrypt the password and save it to S3 """

    aes, key_name = get_new_aes(user, email)
    key = aws_s3_get_key('a/{}'.format(key_name), bucket_name=settings.S3_SECRET_BUCKET, validate=False)

    password = aes.encrypt(password.encode())
    password = base64.b64encode(password)

    key.set_contents_from_string(password)


def get_aliexpress_password(user, email):
    """ Get the encrypt password from S3 and decrypt it """

    aes, key_name = get_new_aes(user, email)
    key = aws_s3_get_key('a/{}'.format(key_name), bucket_name=settings.S3_SECRET_BUCKET)

    password = None

    if key:
        password = key.get_contents_as_string()
        password = base64.decodestring(password)
        password = aes.decrypt(password)

    return password


def delete_aliexpress_password(user, email):
    """ Remove the password file from S3 """

    aes, key_name = get_new_aes(user, email)
    key = aws_s3_get_key('a/{}'.format(key_name), bucket_name=settings.S3_SECRET_BUCKET)

    if key:
        key.delete()
