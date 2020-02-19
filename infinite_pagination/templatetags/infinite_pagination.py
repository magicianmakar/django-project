import copy

from django.template import Library

register = Library()

PAGE_VAR = "page"


@register.inclusion_tag("pagination/infinite_pagination.html", takes_context=True)
def paginate(context):
    try:
        page_obj = context["page_obj"]
    except KeyError:
        return {}

    tag_context = copy.copy(context)  # reuse original context
    tag_context["is_paginated"] = page_obj.has_other_pages()

    if "request" in context:
        getvars = context["request"].GET.copy()
        if PAGE_VAR in getvars:
            del getvars[PAGE_VAR]
        if len(getvars.keys()) > 0:
            tag_context["getvars"] = "&%s" % getvars.urlencode()
        else:
            tag_context["getvars"] = ""
    return tag_context
