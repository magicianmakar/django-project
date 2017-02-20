from django.core.exceptions import PermissionDenied

from leadgalaxy.models import ShopifyStore


def user_can_add(user, obj):
    if not user.is_subuser:
        can = obj.user == user
    else:
        if isinstance(obj, ShopifyStore):
            raise PermissionDenied('Sub-User can not add new stores')

        can = obj.user == user.profile.subuser_parent

        if can:
            if hasattr(obj, 'store'):
                store = obj.store
            else:
                store = None

            if store:
                stores = user.profile.get_shopify_stores(flat=True)
                if store.id not in stores:
                    raise PermissionDenied("You don't have autorization to edit this store.")

    if not can:
        raise PermissionDenied('Unautorized Action (0x{})'.format(abs(hash('add'))))


def user_can_view(user, obj):
    if user.is_superuser:
        return True
    elif not user.is_subuser:
        can = obj.user == user
    else:
        can = obj.user == user.profile.subuser_parent
        if can:
            if isinstance(obj, ShopifyStore):
                store = obj
            elif hasattr(obj, 'store'):
                store = obj.store
            else:
                store = None

            if store:
                stores = user.profile.get_shopify_stores(flat=True)
                if store.id not in stores:
                    raise PermissionDenied("You don't have autorization to view this store.")

    if not can:
        raise PermissionDenied('Unautorized Action (0x{})'.format(hash('view')))


def user_can_edit(user, obj):
    if not user.is_subuser:
        can = obj.user == user
    else:
        if isinstance(obj, ShopifyStore):
            raise PermissionDenied('Sub-User can not edit stores')

        can = obj.user == user.profile.subuser_parent
        if can:
            if hasattr(obj, 'store'):
                store = obj.store
            else:
                store = None

            if store:
                stores = user.profile.get_shopify_stores(flat=True)
                if store.id not in stores:
                    raise PermissionDenied("You don't have autorization to view this store.")

    if not can:
        raise PermissionDenied('Unautorized Action (0x{})'.format(hash('edit')))


def user_can_delete(user, obj):
    if not user.is_subuser:
        can = obj.user == user
    else:
        if isinstance(obj, ShopifyStore):
            raise PermissionDenied('Sub-User can not delete stores')

        can = obj.user == user.profile.subuser_parent

    if not can:
        raise PermissionDenied('Unautorized Action (0x{})'.format(hash('delete')))
