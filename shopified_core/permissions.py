import arrow
import datetime

from django.core.exceptions import PermissionDenied
from django.db.models import Q, Count, Sum
from django.core.cache import cache

from leadgalaxy.models import ShopifyStore
from commercehq_core.models import CommerceHQStore
from woocommerce_core.models import WooStore
from gearbubble_core.models import GearBubbleStore
from groovekart_core.models import GrooveKartStore
from bigcommerce_core.models import BigCommerceStore
from supplements.models import UserSupplementLabel

from lib.exceptions import capture_message


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
                isinstance(obj, GearBubbleStore) or \
                isinstance(obj, BigCommerceStore) or \
                isinstance(obj, GrooveKartStore):
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
                elif isinstance(store, GrooveKartStore):
                    stores = user.profile.get_gkart_stores(flat=True)
                elif isinstance(store, BigCommerceStore):
                    stores = user.profile.get_bigcommerce_stores(flat=True)
                else:
                    return raise_or_return_result("Unknow Store Type", raise_on_error=raise_on_error)

                if store.id not in stores:
                    return raise_or_return_result("You don't have autorization to edit this store.", raise_on_error=raise_on_error)

    if not can:
        return raise_or_return_result("Unauthorized Add Action", raise_on_error=raise_on_error)

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
                    isinstance(obj, GrooveKartStore) or \
                    isinstance(obj, BigCommerceStore) or \
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
                elif isinstance(store, GrooveKartStore):
                    stores = user.profile.get_gkart_stores(flat=True)
                elif isinstance(store, BigCommerceStore):
                    stores = user.profile.get_bigcommerce_stores(flat=True)
                else:
                    return raise_or_return_result("Unknow Store Type", raise_on_error=raise_on_error)

                if store.id not in stores:
                    return raise_or_return_result("You don't have autorization to view this store.", raise_on_error=raise_on_error)

    if not can:
        return raise_or_return_result("Unauthorized View Action", raise_on_error=raise_on_error)

    return can


def user_can_edit(user, obj, raise_on_error=True):
    obj_user = get_object_user(obj)

    if not user.is_subuser:
        can = obj_user == user
    else:
        if isinstance(obj, ShopifyStore) or \
                isinstance(obj, CommerceHQStore) or \
                isinstance(obj, WooStore) or \
                isinstance(obj, GrooveKartStore) or \
                isinstance(obj, BigCommerceStore) or \
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
                elif isinstance(store, GrooveKartStore):
                    stores = user.profile.get_gkart_stores(flat=True)
                elif isinstance(store, BigCommerceStore):
                    stores = user.profile.get_bigcommerce_stores(flat=True)
                else:
                    return raise_or_return_result("Unknow Store Type", raise_on_error=raise_on_error)

                if store.id not in stores:
                    return raise_or_return_result("You don't have autorization to view this store.", raise_on_error=raise_on_error)

    if not can:
        return raise_or_return_result("Unauthorized Edit Action", raise_on_error=raise_on_error)

    return can


def user_can_delete(user, obj, raise_on_error=True):
    obj_user = get_object_user(obj)

    if not user.is_subuser:
        can = obj_user == user
    else:
        if isinstance(obj, ShopifyStore) or \
                isinstance(obj, CommerceHQStore) or \
                isinstance(obj, WooStore) or \
                isinstance(obj, GrooveKartStore) or \
                isinstance(obj, BigCommerceStore) or \
                isinstance(obj, GearBubbleStore):
            return raise_or_return_result("Sub-User can not delete stores", raise_on_error=raise_on_error)

        can = obj_user == user.profile.subuser_parent

    if not can:
        return raise_or_return_result("Unauthorized Delete Action", raise_on_error=raise_on_error)

    return can


def can_add_subuser(user):
    """ Check if the user plan allow him to add a new sub user """

    profile = user.profile

    user_subusers = int(profile.sub_users_limit)
    if user_subusers == -2:
        total_allowed = profile.plan.sub_users_limit
    else:
        total_allowed = user_subusers

    user_subusers_count = profile.get_sub_users_count()

    can_add = True

    if (total_allowed > -1) and (user_subusers_count + 1 > total_allowed):
        if not profile.can('unlimited_subusers.use'):
            can_add = False

    shopify_or_stripe = profile.plan.is_stripe() or profile.plan.is_shopify()
    if not can_add and shopify_or_stripe and profile.plan.extra_subusers:
        can_add = not profile.plan.is_free

    return can_add, total_allowed, user_subusers_count


def can_add_store(user):
    """ Check if the user plan allow him to add a new store """

    profile = user.profile

    if profile.is_subuser:
        return can_add_store(profile.subuser_parent)

    user_stores = int(profile.stores)
    if user_stores == -2:  # Use GroupPlan.stores limit (default)
        total_allowed = profile.plan.stores  # if equal -1 that mean user can add unlimited store
    else:
        total_allowed = user_stores  # Unlimited (-1) Or a positive number of allowed stores defined on this profile (0 or more)

    if total_allowed > -1 and profile.plan.support_addons:
        # Addons doesn't support unlimited stores
        addons_store_limit = profile.addons.all().aggregate(Sum('stores'))['stores__sum'] or 0
        total_allowed += addons_store_limit

    user_count = profile.get_stores_count()

    can_add = True

    if (total_allowed > -1) and (user_count + 1 > total_allowed):
        if not profile.can('unlimited_stores.use'):
            can_add = False

    if not can_add and profile.plan.is_stripe() and profile.plan.extra_stores:
        can_add = not profile.plan.is_free

    return can_add, total_allowed, user_count


def can_add_product(user, ignore_daily_limit=False):
    """ Check if the user plan allow one more product saving """

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
        user_count += profile.user.gearbubbleproduct_set.filter(Q(store=None) | Q(store__is_active=True)).count()
        user_count += profile.user.groovekartproduct_set.filter(Q(store=None) | Q(store__is_active=True)).count()
        user_count += profile.user.bigcommerceproduct_set.filter(Q(store=None) | Q(store__is_active=True)).count()

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
            day_count = 0

        if day_count + 1 > profile.get_config_value('_daily_products_limit', 2000):
            if day_count % 10 == 0 and day_count <= 3000:
                capture_message('Daily limit reached', extra={'user': user.email, 'day_count': day_count})

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
    user_count += profile.user.gearbubbleboard_set.count()
    user_count += profile.user.groovekartboard_set.count()
    user_count += profile.user.bigcommerceboard_set.count()
    can_add = True

    if (total_allowed > -1) and (user_count + 1 > total_allowed):
        if not profile.can('unlimited_boards.use'):
            can_add = False

    return can_add, total_allowed, user_count


def can_add_supplement(user):
    """ Check if the user plan allow one more UserSupplement creation """

    profile = user.profile

    if profile.is_subuser:
        return can_add_supplement(profile.subuser_parent)

    user_supplements = int(profile.user_supplements)
    if user_supplements == -2:
        total_allowed = profile.plan.user_supplements  # -1 mean unlimited
    else:
        total_allowed = user_supplements

    if total_allowed == -1:  # No need for query
        return True, -1, -1

    labels_count_key = 'user_supplement_count_{}'.format(user.id)
    user_count = cache.get(labels_count_key)

    if user_count is None:
        user_count = user.pl_supplements.filter(is_deleted=False).count()
        cache.set(labels_count_key, user_count, timeout=600)

    can_add = True
    if (total_allowed > -1) and (user_count + 1 > total_allowed):
        if not profile.can('unlimited_user_supplements.use'):
            can_add = False

    return can_add, total_allowed, user_count


def can_use_unique_supplement(user, pl_supplement_id=0):
    """ Check if the user plan allow using another PLSupplement
    to create a UserSupplement
    """

    profile = user.profile
    if profile.is_subuser:
        return can_use_unique_supplement(profile.subuser_parent, pl_supplement_id)

    unique_supplements = int(profile.unique_supplements)
    if unique_supplements == -2:
        total_allowed = profile.plan.unique_supplements  # -1 mean unlimited
    else:
        total_allowed = unique_supplements

    if total_allowed == -1:  # No need for query
        return True, -1, -1

    user_count = user.pl_supplements.exclude(
        Q(pl_supplement_id=pl_supplement_id) | Q(pl_supplement__is_active=False)
    ).aggregate(c=Count('pl_supplement', distinct=True))['c']

    can_add = True
    if (total_allowed > -1) and (user_count + 1 > total_allowed):
        if not profile.can('unlimited_unique_supplements.use'):
            can_add = False

    return can_add, total_allowed, user_count


def can_upload_label(user):
    """ Check if the user plan allows uploading a label """

    profile = user.profile

    if profile.is_subuser:
        return can_upload_label(profile.subuser_parent)

    today = datetime.date.today()

    total_allowed_labels = int(profile.label_upload_limit)
    if total_allowed_labels == -2:
        total_allowed = profile.plan.label_upload_limit  # -1 mean unlimited
    else:
        total_allowed = total_allowed_labels

    if total_allowed == -1:  # No need for query
        return True, -1, -1

    labels_count_keys = 'label_limit_count_{}'.format(user.id)
    label_count = cache.get(labels_count_keys)

    if label_count is None:
        label_count = UserSupplementLabel.objects.filter(user_supplement__user=user,
                                                         created_at__month=today.month,
                                                         created_at__year=today.year).count()
        cache.set(labels_count_keys, label_count, timeout=6)

    can_add = True
    if (total_allowed > -1) and (label_count + 1 > total_allowed):
        can_add = False

    return can_add, total_allowed, label_count
