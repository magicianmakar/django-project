from django.contrib import admin
from .models import *
from django import forms

from django.core.urlresolvers import reverse


USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(GroupPlan)
class GroupPlanAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'payment_gateway', 'description', 'permissions_count')

    exclude = ('default_plan',)
    filter_horizontal = ('permissions',)
    prepopulated_fields = {'slug': ('title',)}
    list_filter = ('payment_gateway',)
    readonly_fields = ('register_hash',)
    search_fields = ('title', 'slug', 'description', 'register_hash')

    def view_on_site(self, obj):
        if obj.payment_gateway == 'stripe':
            return '/accounts/register/{}-subscribe'.format(obj.slug)


@admin.register(FeatureBundle)
class FeatureBundleAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'permissions_count')
    filter_horizontal = ('permissions',)
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('register_hash',)
    search_fields = ('title', 'slug', 'register_hash')


@admin.register(UserUpload)
class UserUploadAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('product', 'user')
    search_fields = ('url',)

    def view_on_site(self, obj):
        return obj.url


@admin.register(ShopifyBoard)
class ShopifyBoardAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('products', 'user')
    search_fields = ('title',)


@admin.register(ShopifyProduct)
class ShopifyProductAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'user', 'created_at', 'updated_at')
    raw_id_fields = ('parent_product', 'shopify_export', 'store', 'user', 'default_supplier')
    ordering = ('-updated_at',)
    search_fields = ('data', 'notes', 'price_notification_id', 'shopify_id')

    def store_(self, obj):
        return obj.store.title

    def view_on_site(self, obj):
        return reverse('product_view', kwargs={'pid': obj.id})


@admin.register(ShopifyProductExport)
class ShopifyProductExportAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'created_at')
    search_fields = ('original_url', 'shopify_id')
    raw_id_fields = ('store', 'product')


@admin.register(ProductSupplier)
class ProductSupplierAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'supplier_name', 'is_default', 'created_at')
    search_fields = ('product_url', 'supplier_name', 'supplier_url', 'shopify_id')
    raw_id_fields = ('store', 'product')


@admin.register(ShopifyOrderTrack)
class ShopifyOrderTrackAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'line_id', 'shopify_status', 'store', 'source_id', 'get_source_status',
                    'status_updated_at', 'seen', 'hidden', 'check_count', 'source_tracking',
                    'created_at', 'updated_at')

    list_filter = ('shopify_status', 'source_status', 'seen', 'hidden',)
    search_fields = ('order_id', 'line_id', 'source_id', 'source_tracking', 'data')
    raw_id_fields = ('store', 'user')


@admin.register(ShopifyStore)
class ShopifyStoreAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'is_active', 'shop', 'auto_fulfill', 'created_at', 'updated_at')
    search_fields = ('title', 'api_url', 'store_hash') + USER_SEARCH_FIELDS
    raw_id_fields = ('user',)
    readonly_fields = ('store_hash',)
    list_filter = ('is_active', 'auto_fulfill')


@admin.register(ShopifyWebhook)
class ShopifyWebhookAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'topic', 'call_count', 'created_at', 'updated_at')
    raw_id_fields = ('store',)


@admin.register(AccessToken)
class AccessTokenAdmin(admin.ModelAdmin):
    list_display = ('token', 'user', 'created_at', 'updated_at')
    search_fields = ('token',) + USER_SEARCH_FIELDS
    raw_id_fields = ('user',)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'country', 'timezone', 'status')
    list_filter = ('plan', 'status', 'bundles')
    search_fields = ('emails', 'country', 'timezone', 'ips') + USER_SEARCH_FIELDS
    raw_id_fields = ('user', 'subuser_parent')

    fieldsets = (
        (None, {
            'fields': ('user', 'status', 'plan', 'bundles', 'country', 'timezone',)
        }),

        ('User Settings', {
            'fields': ('config', 'emails', 'ips')
        }),

        ('Sub User', {
            'fields': ('subuser_parent', 'subuser_stores', 'subuser_chq_stores')
        }),

        ('Custom Limits', {
            'description': 'Special Values:<br/>-2: Default Plan/Bundles limit<br/>-1: Unlimited Stores<br/>'
                           '&nbsp;&nbsp;0 or more are the new limits for this user',
            'fields': ('stores', 'products', 'boards'),
        }),

        ('Plan Expire', {
            'classes': ('collapse',),
            'fields': ('plan_after_expire', 'plan_expire_at')
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        self.instance = obj  # Capture instance before the form gets generated
        return super(UserProfileAdmin, self).get_form(request, obj=obj, **kwargs)

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        if db_field.name == 'bundles':
            kwargs['widget'] = forms.widgets.CheckboxSelectMultiple()
        elif db_field.name == 'subuser_stores' and self.instance:
            kwargs['widget'] = forms.widgets.CheckboxSelectMultiple()

            # restrict role queryset to those related to this instance:
            if self.instance.subuser_parent is not None:
                kwargs['queryset'] = self.instance.subuser_parent.profile.get_shopify_stores()
            else:
                kwargs['queryset'] = ShopifyStore.objects.none()

        elif db_field.name == 'subuser_chq_stores' and self.instance:
            kwargs['widget'] = forms.widgets.CheckboxSelectMultiple()

            # restrict role queryset to those related to this instance:
            if self.instance.subuser_parent is not None:
                kwargs['queryset'] = self.instance.subuser_parent.profile.get_chq_stores()
            else:
                kwargs['queryset'] = ShopifyStore.objects.none()

        return super(UserProfileAdmin, self).formfield_for_manytomany(
            db_field, request=request, **kwargs)


@admin.register(AppPermission)
class AppPermissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name', 'description')


@admin.register(PlanRegistration)
class PlanRegistrationAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'user', 'email', 'sender', 'expired', 'created_at', 'updated_at')
    list_filter = ('expired', 'plan', 'bundle')
    search_fields = ('data', 'email', 'register_hash', 'sender__username', 'sender__email') + USER_SEARCH_FIELDS
    raw_id_fields = ('user', 'sender')
    readonly_fields = ('register_hash',)

    def view_on_site(self, obj):
        return '/accounts/register/{}'.format(obj.register_hash)


@admin.register(ShopifyProductImage)
class ShopifyProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'variant', 'store')
    search_fields = ('image',)
    raw_id_fields = ('store',)


@admin.register(AliexpressProductChange)
class AliexpressProductChangeAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'seen', 'hidden', 'created_at', 'updated_at')
    raw_id_fields = ('product', 'user')
    search_fields = ('data',) + USER_SEARCH_FIELDS


@admin.register(PlanPayment)
class PlanPaymentAdmin(admin.ModelAdmin):
    list_display = ('provider', 'payment_id', 'transaction_type', 'fullname',
                    'email', 'user', 'product_title', 'amount', 'created_at')
    list_filter = ('provider', 'transaction_type',)
    search_fields = ('fullname', 'email', 'payment_id', 'data') + USER_SEARCH_FIELDS
    raw_id_fields = ('user',)

    def product_title(self, obj):
        try:
            return json.loads(obj.data)['jvzoo']['cprodtitle']
        except:
            return ''

    def amount(self, obj):
        try:
            return '$ {}'.format(json.loads(obj.data)['jvzoo']['ctransamount'])
        except:
            return ''


@admin.register(DescriptionTemplate)
class DescriptionTemplateAdmin(admin.ModelAdmin):
    list_display = ('user', 'title')


@admin.register(ClippingMagic)
class ClippingMagicAdmin(admin.ModelAdmin):
    list_display = ('user', 'remaining_credits', 'updated_at')
    raw_id_fields = ('user',)
    search_fields = USER_SEARCH_FIELDS


@admin.register(CaptchaCredit)
class CaptchaCreditAdmin(admin.ModelAdmin):
    list_display = ('user', 'remaining_credits', 'updated_at')
    raw_id_fields = ('user',)
    search_fields = USER_SEARCH_FIELDS


@admin.register(AdminEvent)
class AdminEventAdmin(admin.ModelAdmin):
    list_display = ('user', 'event_type', 'target_user', 'created_at')
    raw_id_fields = ('user', 'target_user')
    list_filter = ('event_type',)
    search_fields = USER_SEARCH_FIELDS + ('event_type', 'data', 'target_user__id', 'target_user__username', 'target_user__email')


admin.site.register(ClippingMagicPlan)
admin.site.register(CaptchaCreditPlan)
admin.site.register(PriceMarkupRule)
