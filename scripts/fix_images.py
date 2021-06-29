import datetime

from leadgalaxy.utils import upload_file_to_s3
from supplements.models import UserSupplementLabel


def main():
    images = UserSupplementLabel.objects.filter(updated_at__lte=datetime.date(2021, 7, 9))
    for image in images:
        url = f'https://app.dropified.com/pdf/convert/?url={image.url}&ext=.png'
        image.image_url = upload_file_to_s3(url, image.user_supplement.user.id, prefix='/labels')
    images.save()


if __name__ == '__main__':
    main()
