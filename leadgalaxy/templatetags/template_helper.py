from django import template
from django.utils.safestring import mark_safe
from django.conf import settings

from shopified_core.utils import decode_params, app_link as utils_app_link

import simplejson as json
import re

import arrow

register = template.Library()


@register.simple_tag
def app_setting(name):
    return getattr(settings, name, None)


@register.simple_tag
def app_link(*args, **kwargs):
    return utils_app_link(*args, **kwargs)


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

    date_str = date.humanize()
    user = context['request'].user
    if user.is_authenticated and not bool(user.get_config('use_relative_dates', True)):
        date_str = date.format('MM/DD/YYYY')

    if html:
        return mark_safe('<span class="date itooltip" title="%s">%s</span>' % (
            date.format('YYYY/MM/DD HH:mm:ss'), date_str))
    else:
        return date_str


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
def base64_decode(context, data):
    return decode_params(data)


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
        if type(link) is dict:
            if link.get('src'):
                link = link['src']

            elif link.get('path'):
                link = link['path']

            else:
                return None

        if 'cdn.shopify.com' in link.lower():
            if crop:
                crop = '_crop_{}'.format(crop)

            return re.sub(r'\.(jpe?g|png|gif)(\?.+)?$', r'_{}{}.\1\2'.format(size, crop), link, flags=re.I)
        else:
            return link


@register.simple_tag(takes_context=True)
def price_diff(context, from_, to_, reverse_colors=False, html=True):
    if from_ is not float:
        from_ = float(from_)

    if to_ is not float:
        to_ = float(to_)

    colors = ['red', 'green'] if reverse_colors else ['green', 'red']

    if from_ > to_:
        if to_ > 0:
            if html:
                return mark_safe('<span style="color:%s"><i class="fa fa-sort-desc"></i> %0.0f%%</span>' % (
                    colors[0], (((to_ - from_) * 100.) / to_)))
            else:
                return '%0.0f%%' % (((to_ - from_) * 100.) / to_)
        else:
            if html:
                return mark_safe('<span style="color:%s"><i class="fa fa-sort-desc"></i></span>' % (colors[0]))
            else:
                return ''

    else:
        if from_ > 0:
            if html:
                return mark_safe('<span style="color:%s"><i class="fa fa-sort-asc"></i> +%0.0f%%</span>' % (
                    colors[1], (((to_ - from_) * 100.) / from_)))
            else:
                return '%0.0f%%' % (((to_ - from_) * 100.) / from_)
        else:
            if html:
                return mark_safe('<span style="color:%s"><i class="fa fa-sort-asc"></i></span>' % (colors[1]))
            else:
                return ''


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
def money_format(amount=None, store=None, allow_empty=False, just_value=False):
    currency_format = '${{amount}}'

    if store and getattr(store, 'currency_format', None):
        currency_format = re.sub(r'{{\s*([a-zA-Z_-]+)\s*}}', r'{{\1}}', store.currency_format)

    if just_value:
        currency_format = re.findall(r'(\{\{.+?\}\})', currency_format)[0]

    negative = False
    if amount is not None and amount != '':
        if type(amount) is not float:
            try:
                amount = float(amount)
            except:
                amount = 0.0

        if amount < 0:
            amount = abs(amount)
            negative = True

        amount_no_decimals = '{:,.0f}'.format(round(amount))
        amount = '{:,.2f}'.format(amount)

    else:
        amount = ''
        amount_no_decimals = ''

        if allow_empty:
            return amount

    currency_format = currency_format.replace('{{amount}}', amount)

    if 'amount_' in currency_format:
        currency_format = currency_format.replace('{{amount_no_decimals}}', amount_no_decimals)
        currency_format = currency_format.replace('{{amount_with_comma_separator}}', amount)
        currency_format = currency_format.replace('{{amount_no_decimals_with_comma_separator}}', amount_no_decimals)

    if negative and amount != '0.00':
        currency_format = '- {}'.format(currency_format)

    return currency_format.strip()


@register.filter
def key_value(dict, key):
    return dict.get(key, '')


@register.simple_tag
def user_orders_count(user):
    orders_count = 0

    for store in user.profile.get_shopify_stores()[:10]:
        orders_count += store.get_orders_count(all_orders=True)

    return mark_safe('{}'.format(orders_count))


@register.simple_tag(takes_context=True)
def order_track_status(context, track, html=True):
    if track.source_status_details:
        if ',' in track.source_status_details:
            return mark_safe('<span class="itooltip" title="{}">{}</span>'.format(track.get_source_status_details(), track.get_source_status()))
        else:
            return mark_safe('<b class="itooltip text-danger" title="{}">{}</b>'.format(track.get_source_status(), track.get_source_status_details()))
    elif track.source_status:
        color = ''
        if track.source_status in ['PLACE_ORDER_SUCCESS', 'WAIT_SELLER_SEND_GOODS', 'SELLER_PART_SEND_GOODS', 'WAIT_BUYER_ACCEPT_GOODS', 'FINISH']:
            color = 'text-navy'

        return mark_safe('<b class="{}">{}</b>'.format(color, track.get_source_status()))
    else:
        return mark_safe('<i>Awaiting Sync with Aliexpress</i>')
