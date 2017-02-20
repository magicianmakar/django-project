from django import template
from django.utils.safestring import mark_safe
from django.conf import settings

import simplejson as json
import re

import arrow

register = template.Library()


@register.filter
def key_value(dict, key):
    return dict.get(key, '')


@register.simple_tag
def app_setting(name):
    return getattr(settings, name, None)


@register.simple_tag(takes_context=True)
def date_humanize(context, date, html=True):
    import arrow

    date = arrow.get(date) if date else None
    if not date:
        return ''

    try:
        date = date.to(context['request'].session['django_timezone'])
    except:
        pass

    if html:
        return mark_safe('<span class="date itooltip" title="%s">%s</span>' % (
            date.format('YYYY/MM/DD HH:mm:ss'), date.humanize()))
    else:
        return date.humanize()


@register.filter(name='get_datetime')
def get_datetime(isodate):
    return arrow.get(isodate).datetime


@register.simple_tag(takes_context=True)
def encode_order(context, data, auto):
    data['auto'] = (auto == 'True')
    return json.dumps(data).encode('base64').replace('\n', '')


@register.simple_tag(takes_context=True)
def base64_encode(context, data):
    return data.encode('utf8').encode('base64').replace('\n', '')


@register.simple_tag(takes_context=True)
def json_dumps(context, data):
    from django.utils.html import escapejs

    data = json.dumps(data)
    data = escapejs(data)

    return mark_safe("JSON.parse('{}')".format(data))


@register.simple_tag(takes_context=True)
def remove_link_query(context, link):
    if not link:
        return ''

    if not link.startswith('http'):
        link = u'http://{}'.format(link)

    return re.sub('([?#].*)$', r'', link)


@register.simple_tag
def shopify_image_thumb(link, size='small', crop=''):
    if link:
        if 'cdn.shopify.com' in link.lower():
            if crop:
                crop = '_crop_{}'.format(crop)

            return re.sub(r'\.(jpe?g|png|gif)(\?.+)?$', r'_{}{}.\1\2'.format(size, crop), link, flags=re.I)
        else:
            return link


@register.simple_tag(takes_context=True)
def price_diff(context, from_, to_, reverse_colors=False):
    if from_ is not float:
        from_ = float(from_)

    if to_ is not float:
        to_ = float(to_)

    colors = ['red', 'green'] if reverse_colors else ['green', 'red']

    if from_ > to_:
        if to_ > 0:
            return mark_safe('<span style="color:%s"><i class="fa fa-sort-desc"></i> %0.0f%%</span>' % (
                colors[0], (((to_ - from_) * 100.) / to_)))
        else:
            return mark_safe('<span style="color:%s"><i class="fa fa-sort-desc"></i></span>' % (colors[0]))

    else:
        if from_ > 0:
            return mark_safe('<span style="color:%s"><i class="fa fa-sort-asc"></i> +%0.0f%%</span>' % (
                colors[1], (((to_ - from_) * 100.) / from_)))
        else:
            return mark_safe('<span style="color:%s"><i class="fa fa-sort-asc"></i></span>' % (colors[1]))


@register.simple_tag
def plan_limit(plan, name, attr_name=None):
    limit = getattr(plan, attr_name if attr_name else name)

    if limit == -1:
        limit = 'Unlimited'
    elif limit < 2:
        name = name[:-1]

    return '{} {}'.format(limit, name.title())


@register.simple_tag
def plan_features(plan):
    if not plan.features:
        return ''

    def help_replace(m):
        help = m.group(1)

        if '"' in help:
            help = help.replace('"', '\'')

        return ('<i class="fa fa-fw fa-question-circle" qtip-tooltip="{}" qtip-my="bottom center"'
                'qtip-at="top center" style="font-size:16px;color:#BBB"></i>').format(help)

    import markdown

    features = markdown.markdown(plan.features, extensions=['markdown.extensions.nl2br'])
    features = re.sub(
        r'\|\|([^\|]+)\|\|',
        help_replace,
        features,
    )

    return mark_safe(features)


@register.simple_tag
def render_markdown(text, render_help=True):
    if not text:
        return ''

    def help_replace(m):
        help = m.group(1)

        if '"' in help:
            help = help.replace('"', '\'')

        return ('<i class="fa fa-fw fa-question-circle" qtip-tooltip="{}" qtip-my="bottom center"'
                'qtip-at="top center" style="font-size:16px;color:#BBB"></i>').format(help)

    import markdown

    text = markdown.markdown(text, extensions=['markdown.extensions.nl2br'])

    if render_help:
        text = re.sub(
            r'\|\|([^\|]+)\|\|',
            help_replace,
            text,
        )

    return mark_safe(text)


@register.simple_tag
def money_format(amount=None, store=None):
    currency_format = '${{amount}}'

    if store and getattr(store, 'currency_format', None):
        currency_format = store.currency_format

    if amount is not None and amount != '':
        if type(amount) is not float:
            try:
                amount = float(amount)
            except:
                amount = 0.0

        amount_no_decimals = '{:,.0f}'.format(round(amount))
        amount = '{:,.2f}'.format(amount)

    else:
        amount = ''
        amount_no_decimals = ''

    currency_format = currency_format.replace('{{amount}}', amount)

    if 'amount_' in currency_format:
        currency_format = currency_format.replace('{{amount_no_decimals}}', amount_no_decimals)
        currency_format = currency_format.replace('{{amount_with_comma_separator}}', amount)
        currency_format = currency_format.replace('{{amount_no_decimals_with_comma_separator}}', amount_no_decimals)

    return currency_format.strip()
