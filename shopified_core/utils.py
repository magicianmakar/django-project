import os
import hashlib
import time

from django.conf import settings
from django.core.mail import send_mail
from django.core.cache import cache
from django.contrib.auth.models import User
from django.template import Context, Template
from django.utils.crypto import get_random_string

import bleach


def hash_text(text):
    return hashlib.md5(text).hexdigest()


def random_hash():
    token = get_random_string(32)
    return hashlib.md5(token).hexdigest()


def send_email_from_template(tpl, subject, recipient, data, nl2br=True):
    template_file = os.path.join(settings.BASE_DIR, 'app', 'data', 'emails', tpl)
    template = Template(open(template_file).read())

    ctx = Context(data)

    email_html = template.render(ctx)

    if nl2br:
        email_plain = email_html
        email_html = email_html.replace('\n', '<br />')
    else:
        email_plain = bleach.clean(email_html, tags=[], strip=True).strip().split('\n')
        email_plain = map(lambda l: l.strip(), email_plain)
        email_plain = '\n'.join(email_plain)

    if type(recipient) is not list:
        recipient = [recipient]

    send_mail(subject=subject,
              recipient_list=recipient,
              from_email='"Shopified App" <support@shopifiedapp.com>',
              message=email_plain,
              html_message=email_html)

    return email_html


def login_attempts_exceeded(username):
    tries_key = 'login_attempts_{}'.format(hash_text(username.lower()))
    tries = cache.get(tries_key)
    if tries is None:
        tries = {'count': 1, 'username': username}
    else:
        tries['count'] = tries.get('count', 1) + 1

    cache.set(tries_key, tries, timeout=600)

    if tries['count'] != 1:
        if tries['count'] < 5:
            time.sleep(1)
            return False
        else:
            return True
    else:
        return False


def unlock_account_email(username):
    try:
        if '@' in username:
            user = User.objects.get(email__iexact=username)
        else:
            user = User.objects.get(username__iexact=username)
    except:
        return False

    from django.core.urlresolvers import reverse

    unlock_token = random_hash()
    if cache.get('unlock_email_{}'.format(hash_text(username.lower()))) is not None:
        # Email already sent
        return False

    cache.set('unlock_account_{}'.format(unlock_token), {
        'user': user.id,
        'username': username
    }, timeout=660)

    send_email_from_template(
        tpl='account_unlock_instructions.html',
        subject='Unlock instructions',
        recipient=user.email,
        data={
            'username': user.get_first_name(),
            'unlock_link': reverse('user_unlock', kwargs={'token': unlock_token})
        },
        nl2br=False
    )

    cache.set('unlock_email_{}'.format(hash_text(username.lower())), True, timeout=660)

    return True
