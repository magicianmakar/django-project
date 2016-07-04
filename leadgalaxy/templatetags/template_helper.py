from django import template
from django.template import Context, Template
from django.utils.safestring import mark_safe
from django.conf import settings

import simplejson as json
import re

register = template.Library()


@register.simple_tag
def app_setting(name):
    return getattr(settings, name, None)


@register.simple_tag
def date_humanize(date):
    import arrow

    return arrow.get(date).humanize() if date else None


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


@register.simple_tag(takes_context=True)
def price_diff(context, from_, to_, reverse_colors=False):
    if from_ is not float:
        from_ = float(from_)

    if to_ is not float:
        to_ = float(to_)

    colors = ['red', 'green'] if reverse_colors else ['green', 'red']

    if from_ > to_:
        if to_ > 0:
            return mark_safe('<span style="color:%s"><i class="fa fa-sort-desc"></i> %0.0f%%</span>' % (colors[0], (((to_ - from_) * 100.) / to_)))
        else:
            return mark_safe('<span style="color:%s"><i class="fa fa-sort-desc"></i></span>' % (colors[0]))

    else:
        if from_ > 0:
            return mark_safe('<span style="color:%s"><i class="fa fa-sort-asc"></i> +%0.0f%%</span>' % (colors[1], (((to_ - from_) * 100.) / from_)))
        else:
            return mark_safe('<span style="color:%s"><i class="fa fa-sort-asc"></i></span>' % (colors[1]))


@register.simple_tag
def plan_limit(plan, name):
    limit = getattr(plan, name)

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
