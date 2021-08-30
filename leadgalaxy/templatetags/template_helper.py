from django import template
from django.utils.safestring import mark_safe
from django.conf import settings
from django.utils.html import escapejs
from django.template.defaultfilters import slugify

from article.utils import xss_clean
from shopified_core.utils import (
    decode_params,
    app_link as utils_app_link,
    base64_encode,
    safe_int
)

import simplejson as json
import re
import math
import arrow
import markdown
import random

register = template.Library()


@register.simple_tag
def app_setting(name):
    return getattr(settings, name, None)


@register.filter
def app_setting_filter(name):
    return getattr(settings, name, None)


@register.simple_tag
def app_link(*args, **kwargs):
    return utils_app_link(*args, **kwargs)


@register.simple_tag(takes_context=True)
def date_humanize(context, date, html=True, relative=None):
    date = arrow.get(date) if date else None
    if not date:
        return ''

    try:
        date = date.to(context['request'].session['django_timezone'])
    except:
        pass

    try:
        user = context['request'].user
    except:
        user = None

    date_str = date.humanize()

    if relative is not None:
        if not relative:
            date_str = date.format('MM/DD/YYYY')
    else:
        if user and user.is_authenticated and not bool(user.get_config('use_relative_dates', True)):
            date_str = date.format('MM/DD/YYYY')

    if html:
        return mark_safe('<span class="date itooltip" title="%s">%s</span>' % (
            date.format('YYYY/MM/DD HH:mm:ss'), date_str))
    else:
        return date_str


@register.filter(name='get_datetime')
def get_datetime(isodate):
    return arrow.get(isodate).datetime


@register.filter(expects_localtime=True)
def user_date(date, format='MM.DD.YYYY hh:mmA ZZ'):
    if not date:
        return ''

    date = arrow.get(date)
    return date.format(format)


@register.simple_tag(takes_context=True)
def encode_order(context, data, auto):
    data['auto'] = (auto == 'True')
    return base64_encode(json.dumps(data))


@register.simple_tag(takes_context=True)
def tag_base64_encode(context, data, name='base64_encode'):
    return base64_encode(data)


@register.simple_tag(takes_context=True)
def base64_decode_params(context, data):
    return decode_params(data)


@register.simple_tag(takes_context=True)
def json_dumps(context, data, obfuscate=None):
    data = json.dumps(data)
    if obfuscate:
        rand = random.randint(1, 10)
        ch = random.choice(['\'', 'JSON.parse('])
        sep = '/**/' * rand
        data = sep.join([
            f'/* {obfuscate} {ch} variants_sku */' * rand,
            '\n' * random.randint(0, 4),
            "JSON.parse(",
            f' /* var {obfuscate} = {{ */ ' * rand,
            f"'{escapejs(data)}'",
            '/* ; */' * rand,
            ")",
            f' /* var {obfuscate} = {ch} */ ' * rand
        ])
    else:
        data = f"JSON.parse('{escapejs(data)}')"

    return mark_safe(data)


@register.simple_tag(takes_context=True)
def remove_link_query(context, link):
    if not link:
        return ''

    if not link.startswith('http'):
        link = 'https://{}'.format(link)

    return re.sub('([?#].*)$', r'', link).strip()


@register.filter(name='remove_url_query')
def remove_url_query(link):
    if not link:
        return ''

    if not link.startswith('http'):
        link = 'https://{}'.format(link)

    return re.sub('([?#].*)$', r'', link).strip()


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

        if 'cdn.shopify.com' in link.lower().replace('cdn2', 'cdn'):
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
            return mark_safe(amount)

    currency_format = currency_format.replace('{{amount}}', amount)

    if 'amount_' in currency_format:
        currency_format = currency_format.replace('{{amount_no_decimals}}', amount_no_decimals)
        currency_format = currency_format.replace('{{amount_no_decimals_with_comma_separator}}', amount_no_decimals)
        currency_format = currency_format.replace('{{amount_with_comma_separator}}', amount)
        currency_format = currency_format.replace('{{amount_with_period_separator}}', amount)

    if negative and amount != '0.00':
        currency_format = '- {}'.format(currency_format)

    if currency_format and '<' in currency_format:
        currency_format = xss_clean(currency_format)

    return mark_safe(currency_format.strip())


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
    if track.source_type == 'ebay':
        supplier_name = 'eBay'
    elif track.source_type == 'dropified-print':
        supplier_name = 'Dropified Print'
    elif track.source_type == 'supplements':
        supplier_name = 'Supplements'
    elif track.source_type == 'alibaba':
        supplier_name = 'Alibaba'
    else:
        supplier_name = 'Aliexpress'

    if track.source_status_details:
        if ',' in track.source_status_details:
            return mark_safe('<span class="itooltip" title="{}">{}</span>'.format(track.get_source_status_details(), track.get_source_status()))
        else:
            return mark_safe('<b class="itooltip text-danger" title="{}">{}</b>'.format(track.get_source_status(), track.get_source_status_details()))
    elif track.source_status:
        color = ''
        if track.source_status in ['PLACE_ORDER_SUCCESS', 'WAIT_SELLER_SEND_GOODS', 'SELLER_PART_SEND_GOODS',
                                   'WAIT_BUYER_ACCEPT_GOODS', 'FINISH', 'D_SHIPPED', 'ALIBABA_trade_success',
                                   'ALIBABA_delivering']:
            color = 'text-navy'

        return mark_safe('<b class="{}">{}</b>'.format(color, track.get_source_status()))
    else:
        if track.source_type == 'other':
            return mark_safe('<i>Manual Order</i>')
        else:
            return mark_safe('<i>Awaiting Sync with {}</i>'.format(supplier_name))


@register.simple_tag(takes_context=True)
def order_track_tracking_urls(context, track, html=True):
    tracking = track.get_tracking_link()
    if tracking:
        if type(tracking) is list:
            urls = []
            for i in tracking:
                urls.append(u'<a href="{}" target="_blank">{}</a>'.format(i[1], i[0]))

            return mark_safe('<br>'.join(urls))
        else:
            return mark_safe(u'<a href="{}" target="_blank">{}</a>'.format(tracking, track.source_tracking))
    else:
        return ''


@register.filter
def force_https(url):
    if not url:
        url = ''

    if type(url) is list:
        url = url[0]

    return re.sub(r'https?://', '//', url)


@register.filter()
def sec_to_min(s):
    mins = math.floor(s / 60)
    secs = math.floor(s - (mins * 60))
    return "%d:%02d" % (mins, secs)


@register.filter
def min_value(amount, minimum):
    return min(safe_int(amount), safe_int(minimum))


@register.filter(takes_context=True)
def show_closeable_view(user, view_id):
    view_id = f"_dismissible_{slugify(view_id).replace('-', '_')}"
    return not user.get_config(view_id)


@register.simple_tag(takes_context=True)
def select_option(context, **kwargs):
    request = context['request']
    select = []
    for key, val in kwargs.items():
        select.append(request.GET.get(key) == str(val))

    return 'selected' if select and all(select) else ''
