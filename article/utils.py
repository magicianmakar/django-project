import bleach

from .models import SidebarLink


ALLOW_ATTRS = {
    '*': ['id', 'class', 'style', 'dir'],
    'a': ['href'],
    'img': ['src', 'alt'],
}

ALLOW_TAGS = ['em', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'sub', 'p', 'li',
              'sup', 'blockquote', 'address', 'strong', 'a', 'ol', 'ul', 's', 'u', 'div']

ALLOW_STYLES = ['font-size', 'color', 'margin-left', 'margin-right', 'font-family',
                'background-color', 'text-align']


def xss_clean(text):
    return bleach.clean(text, ALLOW_TAGS, ALLOW_ATTRS, ALLOW_STYLES)


def get_article_link(slug, **kwargs):
    link = SidebarLink.objects.filter(slug=slug).first()
    if not link:
        return {}

    menu = {
        'title': link.title,
        'url': link.link,
        'match': link.link,
        'icon': link.icon,
    }
    for key in kwargs:
        value = kwargs[key]
        if callable(value):
            menu[key] = value(link)
        else:
            menu[key] = value
    return menu
