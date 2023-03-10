import math

from django import template

register = template.Library()


@register.filter(name='phone_number')
def phone_format(n):
    try:
        return '+{}{}'.format(format(int(n[:-1]), ",").replace(",", "-"), n[-1])
    except:
        return 'Not Set'


@register.filter()
def formatSeconds(s):
    if s:
        mins = math.floor(s / 60)
        secs = math.floor(s - (mins * 60))
        return '{:.0f}:{:.0f}'.format(mins, secs)
    else:
        return '00:00'
