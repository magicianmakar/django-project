from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, HttpResponseRedirect, Http404
from django.shortcuts import render, get_object_or_404, redirect

from leadgalaxy.models import ShopifyStore, PlanRegistration
from last_seen.models import LastSeen, clear_interval
from .utils import get_namespace
from .forms import (
    SubUserStoresForm,
    SubuserPermissionsForm,
    SubuserCHQPermissionsForm,
    SubuserWooPermissionsForm,
    SubuserGKartPermissionsForm,
    SubuserBigCommercePermissionsForm,
    SubuserFBPermissionsForm,
    SubuserGooglePermissionsForm,
)
from shopified_core.permissions import can_add_subuser


@login_required
def subusers(request):

    if request.user.is_subuser:
        raise PermissionDenied()

    sub_users = {}

    for sub in User.objects.filter(profile__subuser_parent=request.user):
        try:
            sub.last_seen = LastSeen.objects.when(sub, 'website')
        except:
            sub.last_seen = None

        sub_users[sub.email] = {
            'id': sub.id,
            'username': sub.username,
            'name': sub.get_full_name() if sub.get_full_name() else sub.username,
            'email': sub.email,
            'date_joined': sub.date_joined,
            'last_seen': sub.last_seen,
            'is_invite': False,
        }

        clear_interval(sub)

    for i in PlanRegistration.objects.filter(sender=request.user).filter(Q(user__isnull=True) | Q(user__profile__subuser_parent=request.user)):
        i.have_access = (i.expired and (i.user.profile.subuser_stores.count() or i.user.profile.subuser_chq_stores.count()))

        if not i.have_access and i.email not in sub_users:
            sub_users[i.email] = {
                'id': i.user.id if i.user else '',
                'user': i.user if i.user else '',
                'name': i.user.get_full_name() if i.user else '',
                'email': i.email,
                'created_at': i.created_at,
                'expired': i.expired,
                'is_invite': True,
            }

    sub_users = list(sub_users.values())
    extra_user_cost = request.user.profile.plan.extra_subuser_cost

    can_add, total_allowed, user_subusers_count = can_add_subuser(request.user)

    extra_subusers = can_add and request.user.profile.plan.is_stripe() and \
        user_subusers_count >= total_allowed and \
        total_allowed != -1

    return render(request, 'subusers/manage.html', {
        'sub_users': sub_users,
        'extra_user_cost': extra_user_cost,
        'extra_subusers': extra_subusers,
        'page': 'subusers',
        'breadcrumbs': ['Account', 'Sub Users'],
    })


@login_required
def subusers_perms(request, user_id):
    try:
        user = User.objects.get(id=user_id, profile__subuser_parent=request.user)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except:
        return JsonResponse({'error': 'Unknown Error'}, status=500)

    if request.method == 'POST':
        form = SubUserStoresForm(request.POST,
                                 instance=user.profile,
                                 parent_user=request.user)
        if form.is_valid():
            form.save()

            messages.success(request, 'User permissions updated successfully')
        else:
            messages.error(request, 'Error occurred during user permissions update')

        return HttpResponseRedirect(reverse('{}subusers'.format(get_namespace(request))))

    else:
        form = SubUserStoresForm(instance=user.profile,
                                 parent_user=request.user)

    return render(request, 'subusers/perms.html', {
        'subuser': user,
        'form': form,
        'page': 'subusers',
        'breadcrumbs': ['Account', 'Sub Users'],
    })


@transaction.atomic
@login_required
def subuser_perms_edit(request, user_id):
    subuser = get_object_or_404(User, pk=user_id, profile__subuser_parent=request.user)
    global_permissions = subuser.profile.subuser_permissions.filter(store__isnull=True)
    initial = {'permissions': global_permissions, 'store': None}

    if request.method == 'POST':
        form = SubuserPermissionsForm(request.POST, initial=initial)
        if form.is_valid():
            new_permissions = form.cleaned_data['permissions']
            subuser.profile.subuser_permissions.remove(*global_permissions)
            subuser.profile.subuser_permissions.add(*new_permissions)
            messages.success(request, 'Subuser permissions successfully updated')
            return redirect('{}subuser_perms_edit'.format(get_namespace(request)), user_id)
    else:
        form = SubuserPermissionsForm(initial=initial)

    breadcrumbs = [
        'Account',
        {'title': 'Sub Users', 'url': reverse('{}subusers'.format(get_namespace(request)))},
        subuser.username,
        'Permissions',
    ]

    context = {
        'subuser': subuser,
        'form': form,
        'breadcrumbs': breadcrumbs,
        'page': 'subusers',
    }

    return render(request, 'subusers/perms_edit.html', context)


@transaction.atomic
@login_required
def subuser_store_permissions(request, user_id, store_id):
    store = get_object_or_404(ShopifyStore, pk=store_id, user=request.user)
    subuser = get_object_or_404(User,
                                pk=user_id,
                                profile__subuser_parent=request.user,
                                profile__subuser_stores__pk=store_id)
    subuser_permissions = subuser.profile.subuser_permissions.filter(store=store)
    initial = {'permissions': subuser_permissions, 'store': store}

    if request.method == 'POST':
        form = SubuserPermissionsForm(request.POST, initial=initial)
        if form.is_valid():
            new_permissions = form.cleaned_data['permissions']
            subuser.profile.subuser_permissions.remove(*subuser_permissions)
            subuser.profile.subuser_permissions.add(*new_permissions)
            messages.success(request, 'Subuser permissions successfully updated')
            return redirect('{}subuser_store_permissions'.format(get_namespace(request)), user_id, store_id)
    else:
        form = SubuserPermissionsForm(initial=initial)

    breadcrumbs = [
        'Account',
        {'title': 'Sub Users', 'url': reverse('{}subusers'.format(get_namespace(request)))},
        subuser.username,
        {'title': 'Permissions', 'url': reverse('{}subuser_perms_edit'.format(get_namespace(request)), args=(user_id,))},
        store.title,
    ]

    context = {
        'subuser': subuser,
        'form': form,
        'breadcrumbs': breadcrumbs,
        'page': 'subusers',
    }

    return render(request, 'subusers/store_permissions.html', context)


@transaction.atomic
@login_required
def subuser_chq_store_permissions(request, user_id, store_id):
    store = request.user.commercehqstore_set.filter(pk=store_id).first()
    if not store:
        raise Http404

    subuser = get_object_or_404(User,
                                pk=user_id,
                                profile__subuser_parent=request.user,
                                profile__subuser_chq_stores__pk=store_id)

    subuser_chq_permissions = subuser.profile.subuser_chq_permissions.filter(store=store)
    initial = {'permissions': subuser_chq_permissions, 'store': store}

    if request.method == 'POST':
        form = SubuserCHQPermissionsForm(request.POST, initial=initial)
        if form.is_valid():
            new_permissions = form.cleaned_data['permissions']
            subuser.profile.subuser_chq_permissions.remove(*subuser_chq_permissions)
            subuser.profile.subuser_chq_permissions.add(*new_permissions)
            messages.success(request, 'Subuser permissions successfully updated')
            return redirect('{}subuser_chq_store_permissions'.format(get_namespace(request)), user_id, store_id)
    else:
        form = SubuserCHQPermissionsForm(initial=initial)

    breadcrumbs = [
        'Account',
        {'title': 'Sub Users', 'url': reverse('{}subusers'.format(get_namespace(request)))},
        subuser.username,
        {'title': 'Permissions', 'url': reverse('{}subuser_perms_edit'.format(get_namespace(request)), args=(user_id,))},
        store.title,
    ]

    context = {
        'subuser': subuser,
        'form': form,
        'breadcrumbs': breadcrumbs,
        'page': 'subusers',
    }

    return render(request, 'subusers/chq_store_permissions.html', context)


@transaction.atomic
@login_required
def subuser_woo_store_permissions(request, user_id, store_id):
    store = request.user.woostore_set.filter(pk=store_id).first()
    if not store:
        raise Http404

    subuser = get_object_or_404(User,
                                pk=user_id,
                                profile__subuser_parent=request.user,
                                profile__subuser_woo_stores__pk=store_id)

    subuser_woo_permissions = subuser.profile.subuser_woo_permissions.filter(store=store)
    initial = {'permissions': subuser_woo_permissions, 'store': store}

    if request.method == 'POST':
        form = SubuserWooPermissionsForm(request.POST, initial=initial)
        if form.is_valid():
            new_permissions = form.cleaned_data['permissions']
            subuser.profile.subuser_woo_permissions.remove(*subuser_woo_permissions)
            subuser.profile.subuser_woo_permissions.add(*new_permissions)
            messages.success(request, 'Subuser permissions successfully updated')
            return redirect('{}subuser_woo_store_permissions'.format(get_namespace(request)), user_id, store_id)
    else:
        form = SubuserWooPermissionsForm(initial=initial)

    breadcrumbs = [
        'Account',
        {'title': 'Sub Users', 'url': reverse('{}subusers'.format(get_namespace(request)))},
        subuser.username,
        {'title': 'Permissions', 'url': reverse('{}subuser_perms_edit'.format(get_namespace(request)), args=(user_id,))},
        store.title,
    ]

    context = {
        'subuser': subuser,
        'form': form,
        'breadcrumbs': breadcrumbs,
        'page': 'subusers',
    }

    return render(request, 'subusers/woo_store_permissions.html', context)


@transaction.atomic
@login_required
def subuser_gkart_store_permissions(request, user_id, store_id):
    store = request.user.groovekartstore_set.filter(pk=store_id).first()
    if not store:
        raise Http404

    subuser = get_object_or_404(User,
                                pk=user_id,
                                profile__subuser_parent=request.user,
                                profile__subuser_gkart_stores__pk=store_id)

    subuser_gkart_permissions = subuser.profile.subuser_gkart_permissions.filter(store=store)
    initial = {'permissions': subuser_gkart_permissions, 'store': store}

    if request.method == 'POST':
        form = SubuserGKartPermissionsForm(request.POST, initial=initial)
        if form.is_valid():
            new_permissions = form.cleaned_data['permissions']
            subuser.profile.subuser_gkart_permissions.remove(*subuser_gkart_permissions)
            subuser.profile.subuser_gkart_permissions.add(*new_permissions)
            messages.success(request, 'Subuser permissions successfully updated')
            return redirect('{}subuser_gkart_store_permissions'.format(get_namespace(request)), user_id, store_id)
    else:
        form = SubuserGKartPermissionsForm(initial=initial)

    breadcrumbs = [
        'Account',
        {'title': 'Sub Users', 'url': reverse('{}subusers'.format(get_namespace(request)))},
        subuser.username,
        {'title': 'Permissions', 'url': reverse('{}subuser_perms_edit'.format(get_namespace(request)), args=(user_id,))},
        store.title,
    ]

    context = {
        'subuser': subuser,
        'form': form,
        'breadcrumbs': breadcrumbs,
        'page': 'subusers',
    }

    return render(request, 'subusers/gkart_store_permissions.html', context)


@transaction.atomic
@login_required
def subuser_bigcommerce_store_permissions(request, user_id, store_id):
    store = request.user.bigcommercestore_set.filter(pk=store_id).first()
    if not store:
        raise Http404

    subuser = get_object_or_404(User,
                                pk=user_id,
                                profile__subuser_parent=request.user,
                                profile__subuser_bigcommerce_stores__pk=store_id)

    subuser_bigcommerce_permissions = subuser.profile.subuser_bigcommerce_permissions.filter(store=store)
    initial = {'permissions': subuser_bigcommerce_permissions, 'store': store}

    if request.method == 'POST':
        form = SubuserBigCommercePermissionsForm(request.POST, initial=initial)
        if form.is_valid():
            new_permissions = form.cleaned_data['permissions']
            subuser.profile.subuser_bigcommerce_permissions.remove(*subuser_bigcommerce_permissions)
            subuser.profile.subuser_bigcommerce_permissions.add(*new_permissions)
            messages.success(request, 'Subuser permissions successfully updated')
            return redirect('{}subuser_bigcommerce_store_permissions'.format(get_namespace(request)), user_id, store_id)
    else:
        form = SubuserBigCommercePermissionsForm(initial=initial)

    breadcrumbs = [
        'Account',
        {'title': 'Sub Users', 'url': reverse('{}subusers'.format(get_namespace(request)))},
        subuser.username,
        {'title': 'Permissions', 'url': reverse('{}subuser_perms_edit'.format(get_namespace(request)), args=(user_id,))},
        store.title,
    ]

    context = {
        'subuser': subuser,
        'form': form,
        'breadcrumbs': breadcrumbs,
        'page': 'subusers',
    }

    return render(request, 'subusers/bigcommerce_store_permissions.html', context)


@transaction.atomic
@login_required
def subuser_fb_store_permissions(request, user_id, store_id):
    store = request.user.fbstore_set.filter(pk=store_id).first()
    if not store:
        raise Http404

    subuser = get_object_or_404(User,
                                pk=user_id,
                                profile__subuser_parent=request.user,
                                profile__subuser_fb_stores__pk=store_id)

    subuser_fb_permissions = subuser.profile.subuser_fb_permissions.filter(store=store)
    initial = {'permissions': subuser_fb_permissions, 'store': store}

    if request.method == 'POST':
        form = SubuserFBPermissionsForm(request.POST, initial=initial)
        if form.is_valid():
            new_permissions = form.cleaned_data['permissions']
            subuser.profile.subuser_fb_permissions.remove(*subuser_fb_permissions)
            subuser.profile.subuser_fb_permissions.add(*new_permissions)
            messages.success(request, 'Subuser permissions successfully updated')
            return redirect(f'{get_namespace(request)}subuser_fb_store_permissions', user_id, store_id)
    else:
        form = SubuserFBPermissionsForm(initial=initial)

    breadcrumbs = [
        'Account',
        {'title': 'Sub Users', 'url': reverse(f'{get_namespace(request)}subusers')},
        subuser.username,
        {'title': 'Permissions', 'url': reverse(f'{get_namespace(request)}subuser_perms_edit', args=(user_id,))},
        store.title,
    ]

    context = {
        'subuser': subuser,
        'form': form,
        'breadcrumbs': breadcrumbs,
        'page': 'subusers',
    }

    return render(request, 'subusers/fb_store_permissions.html', context)


@transaction.atomic
@login_required
def subuser_google_store_permissions(request, user_id, store_id):
    store = request.user.googlestore_set.filter(pk=store_id).first()
    if not store:
        raise Http404

    subuser = get_object_or_404(User,
                                pk=user_id,
                                profile__subuser_parent=request.user,
                                profile__subuser_google_stores__pk=store_id)

    subuser_google_permissions = subuser.profile.subuser_google_permissions.filter(store=store)
    initial = {'permissions': subuser_google_permissions, 'store': store}

    if request.method == 'POST':
        form = SubuserGooglePermissionsForm(request.POST, initial=initial)
        if form.is_valid():
            new_permissions = form.cleaned_data['permissions']
            subuser.profile.subuser_google_permissions.remove(*subuser_google_permissions)
            subuser.profile.subuser_google_permissions.add(*new_permissions)
            messages.success(request, 'Subuser permissions successfully updated')
            return redirect(f'{get_namespace(request)}subuser_google_store_permissions', user_id, store_id)
    else:
        form = SubuserGooglePermissionsForm(initial=initial)

    breadcrumbs = [
        'Account',
        {'title': 'Sub Users', 'url': reverse(f'{get_namespace(request)}subusers')},
        subuser.username,
        {'title': 'Permissions', 'url': reverse(f'{get_namespace(request)}subuser_perms_edit', args=(user_id,))},
        store.title,
    ]

    context = {
        'subuser': subuser,
        'form': form,
        'breadcrumbs': breadcrumbs,
        'page': 'subusers',
    }

    return render(request, 'subusers/google_store_permissions.html', context)
