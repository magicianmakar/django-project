from django.contrib import admin
from .models import *
from django.core.urlresolvers import reverse


@admin.register(GroupPlan)
class GroupPlanAdmin(admin.ModelAdmin):
    list_display = ('title', 'montly_price', 'description', 'stores', 'products',
                    'boards', 'slug', 'register_hash', 'permissions_count')

    exclude = ('default_plan',)
    filter_horizontal = ('permissions',)
    prepopulated_fields = {'slug': ('title',)}


@admin.register(FeatureBundle)
class FeatureBundleAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'register_hash', 'permissions_count')
    filter_horizontal = ('permissions',)
    prepopulated_fields = {'slug': ('title',)}


@admin.register(UserUpload)
class UserUploadAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('product',)

    def view_on_site(self, obj):
        return obj.url


@admin.register(ShopifyBoard)
class ShopifyBoardAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('products',)


@admin.register(ShopifyProduct)
class ShopifyProductAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store_', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('parent_product', 'shopify_export', 'store', 'user')
    ordering = ('-updated_at',)

    def store_(self, obj):
        return obj.store.title

    def view_on_site(self, obj):
        return reverse('product_view', kwargs={'pid': obj.id})


@admin.register(ShopifyProductExport)
class ShopifyProductExportAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'created_at')
    raw_id_fields = ('store',)


@admin.register(ShopifyOrder)
class ShopifyOrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'line_id', 'shopify_status', 'store', 'source_id', 'get_source_status',
                    'status_updated_at', 'seen', 'hidden', 'check_count', 'source_tracking',
                    'created_at', 'updated_at')

    list_filter = ('shopify_status', 'source_status', 'seen', 'hidden',)


@admin.register(ShopifyStore)
class ShopifyStoreAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'is_active', 'created_at', 'updated_at')


@admin.register(ShopifyWebhook)
class ShopifyWebhookAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'topic', 'call_count', 'created_at', 'updated_at')


@admin.register(AccessToken)
class AccessTokenAdmin(admin.ModelAdmin):
    list_display = ('token', 'user', 'created_at', 'updated_at')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status')
    list_filter = ('plan', 'status', 'bundles')
    filter_horizontal = ('bundles',)


@admin.register(AppPermission)
class AppPermissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')


@admin.register(PlanRegistration)
class PlanRegistrationAdmin(admin.ModelAdmin):
    list_display = ('plan', 'user', 'register_hash', 'expired', 'created_at', 'updated_at')
    list_filter = ('expired',)


@admin.register(ShopifyProductImage)
class ShopifyProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'variant', 'store')


@admin.register(AliexpressProductChange)
class AliexpressProductChangeAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'seen', 'hidden', 'created_at', 'updated_at')
    raw_id_fields = ('product', 'user')
    list_filter = ('seen', 'hidden',)


@admin.register(PlanPayment)
class PlanPaymentAdmin(admin.ModelAdmin):
    list_display = ('provider', 'payment_id', 'transaction_type', 'fullname',
                    'email', 'user', 'created_at')
    list_filter = ('provider', 'transaction_type',)
