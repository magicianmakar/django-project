import requests

from app.celery_base import celery_app, CaptureFailure
from last_seen.models import UserIpRecord


@celery_app.task(base=CaptureFailure, ignore_result=True)
def update_ip_details(user_ip_id):
    user_ip = UserIpRecord.objects.get(id=user_ip_id)

    rep = requests.get(url=f'https://ipinfo.io/{user_ip.ip}/json')
    if rep.ok:
        data = rep.json()
        if data and not data.get('bogon'):
            user_ip.country = data['country']
            user_ip.city = data['city']
            user_ip.org = data['org']
            user_ip.save()
