from tqdm import tqdm

from shopified_core.commands import DropifiedBaseCommand
from leadgalaxy.models import (
    User,
    ShopifyStore,
    SUBUSER_PERMISSIONS,
    SUBUSER_STORE_PERMISSIONS,
    SUBUSER_CHQ_STORE_PERMISSIONS,
    SUBUSER_WOO_STORE_PERMISSIONS,
    SUBUSER_GKART_STORE_PERMISSIONS,
    SUBUSER_BIGCOMMERCE_STORE_PERMISSIONS,
    SUBUSER_FB_STORE_PERMISSIONS,
    SubuserPermission,
    SubuserCHQPermission,
    SubuserWooPermission,
    SubuserGKartPermission,
    SubuserBigCommercePermission,
    SubuserFBPermission,
)

from commercehq_core.models import CommerceHQStore
from facebook_core.models import FBStore
from woocommerce_core.models import WooStore
from groovekart_core.models import GrooveKartStore
from bigcommerce_core.models import BigCommerceStore


class Command(DropifiedBaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--progress', dest='progress', action='store_true', help='Show progress')
        parser.add_argument(
            '-p', '--perm', dest='selected_permissions', action='append', type=str,
            help='Use only selected permissions')
        parser.add_argument('--global', dest='reload_global', action='store_true', help='Update global permissions')
        parser.add_argument('--stores', dest='reload_stores', action='store_true', help='Update store specific permissions')
        parser.add_argument('--allow-subusers', dest='add_to_subusers', action='store_true', help='Add permissions to all subusers')

    def get_selected_permissions(self, existing_permissions):
        if not self.selected_permissions:
            return existing_permissions

        result = []
        for perm, name in existing_permissions:
            if perm in self.selected_permissions:
                result.append([perm, name])
        return result

    def start_command(self, *args, **options):
        self.progress = options.get('progress')
        self.selected_permissions = options.get('selected_permissions')

        count = 0
        stores = []
        if options.get('reload_stores'):
            stores.append([
                SubuserPermission,
                self.get_selected_permissions(SUBUSER_STORE_PERMISSIONS),
                ShopifyStore.objects.iterator()
            ])
            count += ShopifyStore.objects.count()

            stores.append([
                SubuserCHQPermission,
                self.get_selected_permissions(SUBUSER_CHQ_STORE_PERMISSIONS),
                CommerceHQStore.objects.iterator()
            ])
            count += CommerceHQStore.objects.count()

            stores.append([
                SubuserWooPermission,
                self.get_selected_permissions(SUBUSER_WOO_STORE_PERMISSIONS),
                WooStore.objects.iterator()
            ])
            count += WooStore.objects.count()

            stores.append([
                SubuserGKartPermission,
                self.get_selected_permissions(SUBUSER_GKART_STORE_PERMISSIONS),
                GrooveKartStore.objects.iterator()
            ])
            count += GrooveKartStore.objects.count()

            stores.append([
                SubuserBigCommercePermission,
                self.get_selected_permissions(SUBUSER_BIGCOMMERCE_STORE_PERMISSIONS),
                BigCommerceStore.objects.iterator()
            ])
            count += BigCommerceStore.objects.count()

            stores.append([
                SubuserFBPermission,
                self.get_selected_permissions(SUBUSER_FB_STORE_PERMISSIONS),
                FBStore.objects.iterator()
            ])
            count += FBStore.objects.count()

        subuser_permissions = []
        if options.get('reload_global'):
            subuser_permissions = self.get_selected_permissions(SUBUSER_PERMISSIONS)
            count += len(subuser_permissions)

        if self.progress:
            progress_bar = tqdm(total=count)

        # Create global permissions
        for codename, name in subuser_permissions:
            SubuserPermission.objects.update_or_create(codename=codename, defaults={'name': name})

            if self.progress:
                progress_bar.update(1)

        # Creates per store permissions
        for perms_model, store_perms, query in stores:
            for store in query:
                for codename, name in store_perms:
                    perms_model.objects.update_or_create(store=store, codename=codename, defaults={'name': name})

                if self.progress:
                    progress_bar.update(1)

        if self.progress:
            progress_bar.close()

        # Grants subusers global and store permissions
        if options.get('add_to_subusers') and input('This will add permissions to all subusers, you sure? [y/N] ') == 'y':
            def get_store_perms(store_permissions_query):
                if self.selected_permissions:
                    return store_permissions_query.filter(codename__in=self.selected_permissions)
                return store_permissions_query.all()

            subusers = User.objects.filter(profile__subuser_parent__isnull=False)
            if self.progress:
                progress_bar = tqdm(total=len(subusers))

            for subuser in subusers:
                if self.progress:
                    progress_bar.update(1)

                # Subuser global permissions
                if options.get('reload_global'):
                    global_permission_ids = SubuserPermission.objects.filter(
                        store__isnull=True,
                        codename__in=dict(subuser_permissions).keys()
                    ).values_list('pk', flat=True)
                    subuser.profile.subuser_permissions.add(*global_permission_ids)

                # Subuser per store permissions
                if not options.get('reload_stores'):
                    continue

                for subuser_store in subuser.profile.subuser_stores.all():
                    store_permissions = get_store_perms(subuser_store.subuser_permissions)
                    subuser.profile.subuser_permissions.add(*store_permissions)

                for subuser_store in subuser.profile.subuser_chq_stores.all():
                    store_permissions = get_store_perms(subuser_store.subuser_chq_permissions)
                    subuser.profile.subuser_chq_permissions.add(*store_permissions)

                for subuser_store in subuser.profile.subuser_woo_stores.all():
                    store_permissions = get_store_perms(subuser_store.subuser_woo_permissions)
                    subuser.profile.subuser_woo_permissions.add(*store_permissions)

                for subuser_store in subuser.profile.subuser_gear_stores.all():
                    store_permissions = get_store_perms(subuser_store.subuser_gear_permissions)
                    subuser.profile.subuser_gear_permissions.add(*store_permissions)

                for subuser_store in subuser.profile.subuser_gkart_stores.all():
                    store_permissions = get_store_perms(subuser_store.subuser_gkart_permissions)
                    subuser.profile.subuser_gkart_permissions.add(*store_permissions)

                for subuser_store in subuser.profile.subuser_bigcommerce_stores.all():
                    store_permissions = get_store_perms(subuser_store.subuser_bigcommerce_permissions)
                    subuser.profile.subuser_bigcommerce_permissions.add(*store_permissions)

                for subuser_store in subuser.profile.subuser_fb_stores.all():
                    store_permissions = get_store_perms(subuser_store.subuser_fb_permissions)
                    subuser.profile.subuser_fb_permissions.add(*store_permissions)

            if self.progress:
                progress_bar.close()
