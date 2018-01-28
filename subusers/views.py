from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, HttpResponseRedirect, Http404
from django.shortcuts import render, get_object_or_404, redirect

from leadgalaxy.models import ShopifyStore, PlanRegistration
from .utils import get_namespace
from .forms import SubUserStoresForm, SubuserPermissionsForm, SubuserCHQPermissionsForm, SubuserWooPermissionsForm


@login_required
def subusers(request):
    if not request.user.can('sub_users.use'):
        return render(request, 'upgrade.html')

    if request.user.is_subuser:
        raise PermissionDenied()

    sub_users = User.objects.filter(profile__subuser_parent=request.user)
    invitation = []
    for i in PlanRegistration.objects.filter(sender=request.user).filter(Q(user__isnull=True) | Q(user__profile__subuser_parent=request.user)):
        i.have_access = (i.expired and (i.user.profile.subuser_stores.count() or i.user.profile.subuser_chq_stores.count()))

        invitation.append(i)

    return render(request, 'subusers/manage.html', {
        'sub_users': sub_users,
        'invitation': invitation,
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

            messages.success(request, 'User permissions has been updated')
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
            return redirect('{}subusers.views.subuser_perms_edit'.format(get_namespace(request)), user_id)
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
            return redirect('{}subusers.views.subuser_store_permissions'.format(get_namespace(request)), user_id, store_id)
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
            messages.success(request, 'Subuser permissions successfully {}updated')
            return redirect('{}subusers.views.subuser_chq_store_permissions'.format(get_namespace(request)), user_id, store_id)
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
            return redirect('{}subusers.views.subuser_woo_store_permissions'.format(get_namespace(request)), user_id, store_id)
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
