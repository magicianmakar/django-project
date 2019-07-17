from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.shortcuts import render

from shopified_core import permissions
from leadgalaxy.models import DescriptionTemplate, PriceMarkupRule


@login_required
def home_page_view(request):
    user = request.user

    config = user.models_user.profile.get_config()

    can_add, total_allowed, user_count = permissions.can_add_store(user)

    extra_stores = can_add and user.profile.plan.is_stripe() and \
        user.profile.get_stores_count() >= total_allowed and \
        total_allowed != -1

    add_store_btn = not user.is_subuser \
        and (can_add or user.profile.plan.extra_stores) \
        and not user.profile.from_shopify_app_store()

    pending_sub = user.shopifysubscription_set.filter(status='pending')
    if len(pending_sub):
        charge = pending_sub[0].refresh()
        if charge.status == 'pending':
            request.session['active_subscription'] = charge.id
            return HttpResponseRedirect(charge.confirmation_url)

    templates = DescriptionTemplate.objects.filter(user=user.models_user).defer('description')
    markup_rules = PriceMarkupRule.objects.filter(user=user.models_user)

    return render(request, 'home/index.html', {
        'config': config,
        'extra_stores': extra_stores,
        'add_store_btn': add_store_btn,
        'templates': templates,
        'markup_rules': markup_rules,
        'settings_tab': request.path == '/settings',
        'page': 'index',
        'selected_menu': 'account:stores',
        'user_statistics': cache.get('user_statistics_{}'.format(user.id)),
        'breadcrumbs': ['Stores']
    })
