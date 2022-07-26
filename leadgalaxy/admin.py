import csv

import simplejson as json
from adminsortable2.admin import SortableAdminMixin

from django import forms
from django.contrib import admin
from django.urls import reverse
from django.http import HttpResponse

from .models import (
    AccessToken,
    AdminEvent,
    AppPermission,
    CaptchaCredit,
    CaptchaCreditPlan,
    ClippingMagic,
    ClippingMagicPlan,
    DescriptionTemplate,
    FeatureBundle,
    GroupPlan,
    GroupPlanChangeLog,
    PlanPayment,
    PlanRegistration,
    AccountRegistration,
    PriceMarkupRule,
    ProductSupplier,
    ShopifyBoard,
    ShopifyOrderTrack,
    ShopifyProduct,
    ShopifyProductImage,
    ShopifyStore,
    ShopifyWebhook,
    SubuserPermission,
    SubuserCHQPermission,
    SubuserWooPermission,
    SubuserGearPermission,
    SubuserGKartPermission,
    SubuserBigCommercePermission,
    SubuserEbayPermission,
    SubuserFBPermission,
    SubuserGooglePermission,
    UserAddress,
    UserBlackSampleTracking,
    UserCompany,
    UserProfile,
    UserUpload,
    DashboardVideo,
)

USER_SEARCH_FIELDS = ('user__id', 'user__username', 'user__email')


@admin.register(GroupPlan)
class GroupPlanAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'payment_gateway', 'monthly_price', 'trial_days', 'permissions_count', 'revision')

    exclude = ('default_plan',)
    prepopulated_fields = {'slug': ('title',)}
    list_filter = ('free_plan', 'payment_gateway', 'payment_interval', 'show_in_plod_app', 'revision', 'single_charge', 'hidden', 'locked',
                   'support_addons')
    readonly_fields = ('register_hash',)
    search_fields = ('title', 'slug', 'description', 'register_hash')

    def view_on_site(self, obj):
        if obj.payment_gateway == 'stripe':
            return '/accounts/register/{}-subscribe'.format(obj.slug)

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        if db_field.name in ['permissions', 'goals']:
            kwargs['widget'] = forms.widgets.CheckboxSelectMultiple()

        return super().formfield_for_manytomany(db_field, request=request, **kwargs)

    def get_fields(self, request, obj=None, **kwargs):
        fields = super().get_fields(request, obj, **kwargs)
        fields.remove('parent_plan')

        permissions_index = fields.index("permissions")
        fields.insert(permissions_index, 'parent_plan')

        return fields

    class Media:
        js = (
            'shopified/js/admin_groupplan.js',  # handle permissions UI
        )


@admin.register(GroupPlanChangeLog)
class GroupPlanChangeLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'changed_at', 'updated_at')
    list_filter = ('plan',)
    raw_id_fields = ('user',)


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
    raw_id_fields = ('parent_product', 'store', 'user', 'default_supplier', 'user_supplement',)
    ordering = ('-updated_at',)
    search_fields = ('data', 'notes', 'monitor_id', 'shopify_id')

    def store_(self, obj):
        return obj.store.title

    def view_on_site(self, obj):
        return reverse('product_view', kwargs={'pid': obj.id})


@admin.register(ProductSupplier)
class ProductSupplierAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'store', 'supplier_name', 'is_default', 'created_at')
    search_fields = ('product_url', 'supplier_name', 'supplier_url', 'shopify_id')
    raw_id_fields = ('store', 'product')


@admin.register(ShopifyOrderTrack)
class ShopifyOrderTrackAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'line_id', 'shopify_status', 'store', 'source_id', 'get_source_status',
                    'status_updated_at', 'seen', 'hidden', 'check_count', 'source_tracking', 'source_type',
                    'created_at', 'updated_at')

    search_fields = ('order_id', 'line_id', 'source_id', 'source_tracking', 'data')
    raw_id_fields = ('store', 'user')


@admin.register(ShopifyStore)
class ShopifyStoreAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'is_active', 'shop', 'auto_fulfill', 'created_at', 'updated_at', 'uninstalled_at')
    search_fields = ('title', 'api_url', 'store_hash') + USER_SEARCH_FIELDS
    raw_id_fields = ('user',)
    readonly_fields = ('store_hash', 'created_at', 'updated_at', 'uninstalled_at')
    list_filter = ('is_active', 'auto_fulfill', 'version', 'created_at', 'uninstalled_at')


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
    list_display = ('user', 'email', 'plan', 'tz', 'date', 'updated_at')
    list_filter = ('plan', 'plan__payment_gateway', 'status', 'bundles', 'shopify_app_store', 'sync_delay_notify',
                   'shopify_app_store', 'private_label')
    search_fields = ('emails', 'country', 'timezone', 'ips') + USER_SEARCH_FIELDS
    raw_id_fields = ('user', 'subuser_parent')

    fieldsets = (
        (None, {
            'fields': ('user', 'status', 'plan', 'bundles', 'addons', 'country', 'timezone', 'shopify_app_store', 'private_label', 'supplier')
        }),

        ('User Settings', {
            'fields': ('config', 'tags', 'sync_delay_notify', 'emails', 'ips')
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

    def email(self, instance):
        return instance.user.email

    def date(self, instance):
        return instance.user.date_joined

    def tz(self, instance):
        return '{} | {}'.format(instance.country, instance.timezone).strip(' |')

    def get_form(self, request, obj=None, **kwargs):
        self.instance = obj  # Capture instance before the form gets generated
        return super(UserProfileAdmin, self).get_form(request, obj=obj, **kwargs)

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        if db_field.name in ['bundles', 'addons']:
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

    def save_model(self, request, profile, *args, **kwargs):
        profile.sync_tags()

        super(UserProfileAdmin, self).save_model(request, profile, *args, **kwargs)


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


@admin.register(AccountRegistration)
class AccountRegistrationAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'user', 'expired', 'created_at', 'updated_at')
    list_filter = ('expired',)
    search_fields = ('register_hash',) + USER_SEARCH_FIELDS
    raw_id_fields = ('user',)
    readonly_fields = ('register_hash',)

    def view_on_site(self, obj):
        return reverse('account_password_setup', kwargs={'register_id': obj.register_hash})


@admin.register(ShopifyProductImage)
class ShopifyProductImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'variant', 'store')
    search_fields = ('image',)
    raw_id_fields = ('store',)


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
    list_display = ('user', 'event_type', 'target_user', 'details', 'created_at')
    raw_id_fields = ('user', 'target_user')
    list_filter = ('event_type',)
    search_fields = USER_SEARCH_FIELDS + ('event_type', 'data', 'target_user__id', 'target_user__username', 'target_user__email')

    def details(self, obj):
        try:
            data = json.loads(obj.data)

            if data.get('bundle'):
                return data['bundle']
            elif data.get('new_plan'):
                return data.get('new_plan')
            elif data.get('amount'):
                return '$%0.2f' % data.get('amount')
            elif data.get('query'):
                return data.get('query')
            elif data.get('plan'):
                return '{} - {}'.format(data.get('plan'), data.get('email'))
            elif data.get('transaction_id'):
                return '{} => ${}'.format(data.get('transaction_id'), data.get('amount'))
        except:
            pass

        return ''


@admin.register(UserCompany)
class UserCompanyAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'address_line1', 'address_line2', 'city', 'state', 'country', 'zip_code', 'vat', )
    search_fields = ('name',)


@admin.register(UserBlackSampleTracking)
class UserBlackSampleTrackingAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'tracking_number', 'tracking_url', 'created_at', 'updated_at')
    search_fields = USER_SEARCH_FIELDS + ('tracking_number', 'tracking_url')
    list_filter = ('name', 'created_at', 'updated_at')
    raw_id_fields = ('user',)


class SamplesPlanListFilter(admin.SimpleListFilter):
    title = 'Plan'
    parameter_name = 'profile__plan'

    def lookups(self, request, model_admin):
        choices = []

        try:
            perm = AppPermission.objects.get(name='supplement_samples.use')
        except:
            return choices

        for plan in perm.groupplan_set.all():
            choices.append([plan.id, plan.title])

        return choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(profile__plan_id=self.value())


@admin.register(UserAddress)
class UserAddressAdmin(admin.ModelAdmin):
    list_display = ('id', 'email', 'name', 'address_line1', 'address_line2', 'city', 'state', 'country', 'zip_code', 'phone', )
    search_fields = ('profile__user__id', 'profile__user__username', 'profile__user__email', 'name')
    list_filter = [SamplesPlanListFilter]

    actions = ["export_as_csv"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        try:
            perm = AppPermission.objects.get(name='supplement_samples.use')
            qs = qs.filter(profile__plan_id__in=[i.id for i in perm.groupplan_set.all()])
        except AppPermission.DoesNotExist:
            pass

        return qs

    def export_as_csv(self, request, queryset):

        meta = self.model._meta
        field_names = [field.name for field in meta.fields]

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename=users-address-export.csv'
        writer = csv.writer(response)

        writer.writerow(field_names + ['email'])
        for obj in queryset:
            row = [getattr(obj, field) for field in field_names]
            row.append(obj.profile.first().user.email)

            writer.writerow(row)

        return response

    export_as_csv.short_description = "Export Selected"

    def email(self, instance):
        try:
            return instance.profile.first().user.email
        except:
            return 'N/A'


@admin.register(SubuserPermission)
class SubuserPermissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'codename', 'name', 'store')
    raw_id_fields = ('store',)
    search_fields = ('name',)


@admin.register(SubuserCHQPermission)
class SubuserCHQPermissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'codename', 'name', 'store')
    raw_id_fields = ('store',)
    search_fields = ('name',)


@admin.register(SubuserWooPermission)
class SubuserWooPermissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'codename', 'name', 'store')
    raw_id_fields = ('store',)
    search_fields = ('name',)


@admin.register(SubuserGearPermission)
class SubuserGearPermissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'codename', 'name', 'store')
    raw_id_fields = ('store',)
    search_fields = ('name',)


@admin.register(SubuserBigCommercePermission)
class SubuserBigCommercePermissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'codename', 'name', 'store')
    raw_id_fields = ('store',)
    search_fields = ('name',)


@admin.register(SubuserEbayPermission)
class SubuserEbayPermission(admin.ModelAdmin):
    list_display = ('id', 'codename', 'name', 'store')
    raw_id_fields = ('store',)
    search_fields = ('name',)


@admin.register(SubuserFBPermission)
class SubuserFBPermission(admin.ModelAdmin):
    list_display = ('id', 'codename', 'name', 'store')
    raw_id_fields = ('store',)
    search_fields = ('name',)


@admin.register(SubuserGooglePermission)
class SubuserGooglePermission(admin.ModelAdmin):
    list_display = ('id', 'codename', 'name', 'store')
    raw_id_fields = ('store',)
    search_fields = ('name',)


@admin.register(DashboardVideo)
class DashboardVideoAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = ('url', 'title', 'store_type')
    list_filter = ('store_type',)
    search_fields = ('url', 'title', 'store_type')

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        if db_field.name == 'plans':
            kwargs['widget'] = forms.widgets.CheckboxSelectMultiple()

        return super().formfield_for_manytomany(db_field, request=request, **kwargs)


@admin.register(SubuserGKartPermission)
class SubuserGKartPermissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'codename', 'name', 'store')
    raw_id_fields = ('store',)
    search_fields = ('name',)


admin.site.register(ClippingMagicPlan)
admin.site.register(CaptchaCreditPlan)
admin.site.register(PriceMarkupRule)
