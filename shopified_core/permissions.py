from django.core.exceptions import PermissionDenied

from leadgalaxy.models import ShopifyStore
from commercehq_core.models import CommerceHQStore
from woocommerce_core.models import WooStore
from gearbubble_core.models import GearBubbleStore


def get_object_user(obj):
    if hasattr(obj, 'user'):
        return obj.user
    else:
        store = obj.store
        if not store and hasattr(obj, 'product'):
            store = obj.product.store

        return store.user


def raise_or_return_result(msg, raise_on_error):
    if raise_on_error:
        raise PermissionDenied(msg)

    return False


def user_can_add(user, obj, raise_on_error=True):
    obj_user = get_object_user(obj)

    if not user.is_subuser:
        can = obj_user == user
    else:
        if isinstance(obj, ShopifyStore) or \
                isinstance(obj, CommerceHQStore) or \
                isinstance(obj, WooStore) or \
                isinstance(obj, GearBubbleStore):
            return raise_or_return_result("Sub-User can not add new stores", raise_on_error=raise_on_error)

        can = obj_user == user.profile.subuser_parent

        if can:
            if hasattr(obj, 'store'):
                store = obj.store
            else:
                store = None

            if store:
                if isinstance(store, ShopifyStore):
                    stores = user.profile.get_shopify_stores(flat=True)
                elif isinstance(store, CommerceHQStore):
                    stores = user.profile.get_chq_stores(flat=True)
                elif isinstance(store, WooStore):
                    stores = user.profile.get_woo_stores(flat=True)
                elif isinstance(store, GearBubbleStore):
                    stores = user.profile.get_gear_stores(flat=True)
                else:
                    return raise_or_return_result("Unknow Store Type", raise_on_error=raise_on_error)

                if store.id not in stores:
                    return raise_or_return_result("You don't have autorization to edit this store.", raise_on_error=raise_on_error)

    if not can:
        return raise_or_return_result("Unautorized Add Action", raise_on_error=raise_on_error)

    return can


def user_can_view(user, obj, raise_on_error=True, superuser_can=True):
    obj_user = get_object_user(obj)

    if superuser_can and user.is_superuser:
        return True
    elif not user.is_subuser:
        can = obj_user == user
    else:
        can = obj_user == user.profile.subuser_parent
        if can:
            if isinstance(obj, ShopifyStore) or \
                    isinstance(obj, CommerceHQStore) or \
                    isinstance(obj, WooStore) or \
                    isinstance(obj, GearBubbleStore):
                store = obj
            elif hasattr(obj, 'store'):
                store = obj.store
            else:
                store = None

            if store:
                if isinstance(store, ShopifyStore):
                    stores = user.profile.get_shopify_stores(flat=True)
                elif isinstance(store, CommerceHQStore):
                    stores = user.profile.get_chq_stores(flat=True)
                elif isinstance(store, WooStore):
                    stores = user.profile.get_woo_stores(flat=True)
                elif isinstance(store, GearBubbleStore):
                    stores = user.profile.get_gear_stores(flat=True)
                else:
                    return raise_or_return_result("Unknow Store Type", raise_on_error=raise_on_error)

                if store.id not in stores:
                    return raise_or_return_result("You don't have autorization to view this store.", raise_on_error=raise_on_error)

    if not can:
        return raise_or_return_result("Unautorized View Action", raise_on_error=raise_on_error)

    return can


def user_can_edit(user, obj, raise_on_error=True):
    obj_user = get_object_user(obj)

    if not user.is_subuser:
        can = obj_user == user
    else:
        if isinstance(obj, ShopifyStore) or \
                isinstance(obj, CommerceHQStore) or \
                isinstance(obj, WooStore) or \
                isinstance(obj, GearBubbleStore):
            return raise_or_return_result("Sub-User can not edit stores", raise_on_error=raise_on_error)

        can = obj_user == user.profile.subuser_parent
        if can:
            if hasattr(obj, 'store'):
                store = obj.store
            else:
                store = None

            if store:
                if isinstance(store, ShopifyStore):
                    stores = user.profile.get_shopify_stores(flat=True)
                elif isinstance(store, CommerceHQStore):
                    stores = user.profile.get_chq_stores(flat=True)
                elif isinstance(store, WooStore):
                    stores = user.profile.get_woo_stores(flat=True)
                elif isinstance(store, GearBubbleStore):
                    stores = user.profile.get_gear_stores(flat=True)
                else:
                    return raise_or_return_result("Unknow Store Type", raise_on_error=raise_on_error)

                if store.id not in stores:
                    return raise_or_return_result("You don't have autorization to view this store.", raise_on_error=raise_on_error)

    if not can:
        return raise_or_return_result("Unautorized Edit Action", raise_on_error=raise_on_error)

    return can


def user_can_delete(user, obj, raise_on_error=True):
    obj_user = get_object_user(obj)

    if not user.is_subuser:
        can = obj_user == user
    else:
        if isinstance(obj, ShopifyStore) or \
                isinstance(obj, CommerceHQStore) or \
                isinstance(obj, WooStore) or \
                isinstance(obj, GearBubbleStore):
            return raise_or_return_result("Sub-User can not delete stores", raise_on_error=raise_on_error)

        can = obj_user == user.profile.subuser_parent

    if not can:
        return raise_or_return_result("Unautorized Delete Action", raise_on_error=raise_on_error)

    return can


def can_add_store(user):
    """ Check if the user plan allow him to add a new store """

    profile = user.profile

    if profile.is_subuser:
        return can_add_store(profile.subuser_parent)

    user_stores = int(profile.stores)
    if user_stores == -2:  # Use GroupPlan.stores limit (default)
        total_allowed = profile.plan.stores  # if equal -1 that mean user can add unlimited store
    else:
        total_allowed = user_stores

    user_count = profile.user.shopifystore_set.filter(is_active=True).count()
    user_count += profile.user.commercehqstore_set.filter(is_active=True).count()
    user_count += profile.user.woostore_set.filter(is_active=True).count()
    user_count += profile.user.gearbubblestore_set.filter(is_active=True).count()

    can_add = True

    if (total_allowed > -1) and (user_count + 1 > total_allowed):
        if not profile.can('unlimited_stores.use'):
            can_add = False

    if not can_add and profile.plan.is_stripe() and profile.plan.extra_stores:
        can_add = not profile.plan.is_free

    return can_add, total_allowed, user_count


def can_add_product(user, ignore_daily_limit=False):
    """ Check if the user plan allow one more product saving """

    import arrow
    from django.db.models import Q
    from django.core.cache import cache

    profile = user.profile

    if profile.is_subuser:
        return can_add_product(profile.subuser_parent)

    user_products = int(profile.products)
    if user_products == -2:
        total_allowed = profile.plan.products  # -1 mean unlimited
    else:
        total_allowed = user_products

    products_count_key = 'product_count_{}'.format(user.id)
    user_count = cache.get(products_count_key)

    if user_count is None:
        user_count = profile.user.shopifyproduct_set.filter(Q(store=None) | Q(store__is_active=True)).count()
        user_count += profile.user.commercehqproduct_set.filter(Q(store=None) | Q(store__is_active=True)).count()
        user_count += profile.user.wooproduct_set.filter(Q(store=None) | Q(store__is_active=True)).count()

        cache.set(products_count_key, user_count, timeout=600)

    can_add = True

    if (total_allowed > -1) and (user_count + 1 > total_allowed):
        if not profile.can('unlimited_products.use'):
            can_add = False

    if can_add and not ignore_daily_limit:
        # Check daily limit
        now = arrow.utcnow()
        limit_key = 'product_day_limit-{u.id}-{t.day}-{t.month}'.format(u=user, t=now)

        day_count = cache.get(limit_key)
        if day_count is None:
            start, end = now.span('day')
            day_count = profile.user.shopifyproduct_set.filter(created_at__gte=start.datetime, created_at__lte=end.datetime).count()
            day_count += profile.user.commercehqproduct_set.filter(created_at__gte=start.datetime, created_at__lte=end.datetime).count()
            day_count += profile.user.wooproduct_set.filter(created_at__gte=start.datetime, created_at__lte=end.datetime).count()

        if day_count + 1 > profile.get_config_value('_daily_products_limit', 2000):
            from raven.contrib.django.raven_compat.models import client as raven_client

            if day_count % 10 == 0 and day_count <= 3000:
                raven_client.captureMessage('Daily limit reached', extra={'user': user.email, 'day_count': day_count})

            can_add = False

        cache.set(limit_key, day_count + 1, timeout=86400)

    return can_add, total_allowed, user_count


def can_add_board(user):
    """ Check if the user plan allow adding one more Board """

    profile = user.profile

    if profile.is_subuser:
        return can_add_board(profile.subuser_parent)

    user_boards = int(profile.boards)
    if user_boards == -2:
        total_allowed = profile.plan.boards  # -1 mean unlimited
    else:
        total_allowed = user_boards

    user_count = profile.user.shopifyboard_set.count()
    user_count += profile.user.commercehqboard_set.count()
    user_count += profile.user.wooboard_set.count()
    can_add = True

    if (total_allowed > -1) and (user_count + 1 > total_allowed):
        if not profile.can('unlimited_boards.use'):
            can_add = False

    return can_add, total_allowed, user_count
