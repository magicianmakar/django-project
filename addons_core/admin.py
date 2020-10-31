from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from adminsortable2.admin import SortableAdminMixin
from adminsortable2.admin import SortableInlineAdminMixin

from .forms import AddonForm, AddonPriceAdminForm
from .models import Category, Addon, AddonBilling, AddonPrice, AddonUsage


class FormWithRequestMixin:
    def get_form(self, request, obj=None, **kwargs):
        ModelForm = super().get_form(request, obj, **kwargs)

        class ModelFormWithRequest(ModelForm):
            def __init__(self, *args, **kwargs):
                self.request = kwargs.pop('request', None)
                super().__init__(*args, **kwargs)

        class CustomModelForm(ModelFormWithRequest):
            def __new__(cls, *args, **kwargs):
                kwargs['request'] = request
                return ModelFormWithRequest(*args, **kwargs)

        return CustomModelForm


class PreventBillingDeleteMixin:
    delete_extra_search = {'billings__subscriptions__isnull': False}
    delete_not_allowed_name = 'title'

    def has_delete_permission(self, request, obj=None):
        if 'can_delete' in request.POST:
            return request.POST['can_delete']

        # Method is called for each obj in admin list, this prevents extra queries
        if not request.POST.get('action') == 'delete_selected' and (
                not obj or '/delete' not in request.path):
            return True

        obj_ids = request.POST.getlist('_selected_action') or [obj.id]
        not_allowed_objects = self.model.objects.filter(
            id__in=obj_ids, **self.delete_extra_search
        ).values(self.delete_not_allowed_name).distinct()

        post = request.POST.copy()
        if len(not_allowed_objects):
            not_allowed_objects = ', '.join([
                obj[self.delete_not_allowed_name] for obj in not_allowed_objects
            ])
            messages.add_message(
                request,
                messages.ERROR,
                f"Records tying addons to subscriptions cannot be deleted: {not_allowed_objects}"
            )

            # Cache response for object
            post['can_delete'] = False
            request.POST = post
            return False

        post['can_delete'] = True
        request.POST = post
        return True


@admin.register(Category)
class CategoryAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'slug',
        'is_visible',
        'created_at',
        'updated_at',
    )
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ('slug', 'title')
    date_hierarchy = 'created_at'


class AddonBillingInline(SortableInlineAdminMixin, admin.TabularInline):
    model = AddonBilling
    extra = 1

    def links(self, instance):
        if not instance.id:
            return ''

        url = reverse('admin:addons_core_addonbilling_change', args=(instance.id,))
        # … or if you want to include other fields:
        return format_html(u'<a href="{}">See Prices</a>', url)

    readonly_fields = ('links',)


@admin.register(Addon)
class AddonAdmin(PreventBillingDeleteMixin, FormWithRequestMixin, admin.ModelAdmin):
    delete_extra_search = {'billings__subscriptions__isnull': False}
    delete_not_allowed_name = 'title'

    form = AddonForm
    change_form_template = 'addons/admin/addon_change_form.html'
    list_display = (
        'title',
        'slug',
        'addon_hash',
        'hidden',
        'created_at',
        'updated_at',
        'link_actions',
    )
    prepopulated_fields = {'slug': ('title',)}
    list_filter = ('hidden', 'created_at', 'updated_at')
    search_fields = ('slug',)
    filter_horizontal = ('categories', 'permissions')
    date_hierarchy = 'created_at'
    inlines = (AddonBillingInline,)

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields
        return self.readonly_fields + ('stripe_product_id',)

    def link_actions(self, obj):
        permalink = f"""
            <a href="#" onclick="this.children[0].style.display='';
                                 this.children[0].select();
                                 document.execCommand('copy');
                                 this.children[0].style.display='none'">
                Copy Permalink
                <input type="text" style="display: none;"
                       value="{obj.permalink}">
            </a>
        """

        upsell_anonymous = f"""
            <a href="#" onclick="this.children[0].style.display='';
                                 this.children[0].select();
                                 document.execCommand('copy');
                                 this.children[0].style.display='none'">
                Copy Upsell Sign Up
                <input type="text" style="display: none;"
                       value="{obj.upsell_anonymous}">
            </a>
        """

        upsell_user = f"""
            <a href="#" onclick="this.children[0].style.display='';
                                 this.children[0].select();
                                 document.execCommand('copy');
                                 this.children[0].style.display='none'">
                Copy Upsell Logged In
                <input type="text" style="display: none;"
                       value="{obj.upsell_user}">
            </a>
        """
        return format_html(' - '.join([permalink, upsell_anonymous, upsell_user]))
    link_actions.allow_tags = True
    link_actions.short_description = 'Actions'


class TrialsFilter(admin.SimpleListFilter):
    title = 'trial days'
    parameter_name = 'trials'

    def lookups(self, request, model_admin):
        return (
            ('trial_period_days__gt', 'With Trial Days'),
            ('trial_period_days', 'Without Trial Days'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(**{value: 0})


class AddonPriceInline(SortableInlineAdminMixin, admin.TabularInline):
    model = AddonPrice
    form = AddonPriceAdminForm
    extra = 1
    can_delete = False


@admin.register(AddonBilling)
class AddonBillingAdmin(PreventBillingDeleteMixin, admin.ModelAdmin):
    delete_extra_search = {'subscriptions__isnull': False}
    delete_not_allowed_name = 'addon__title'

    list_display = ('billing_title', 'interval_count', 'get_interval_display', 'is_active', 'trial_period_days', 'expire_at')
    list_filter = (TrialsFilter, 'is_active', 'addon')
    search_fields = ('addon__id', 'addon__title')
    inlines = (AddonPriceInline,)

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('interval', 'interval_count')
        return self.readonly_fields


@admin.register(AddonPrice)
class AddonPriceAdmin(PreventBillingDeleteMixin, admin.ModelAdmin):
    delete_extra_search = {'billing__subscriptions__isnull': False}
    delete_not_allowed_name = 'billing__addon__title'
    addon_relation = 'billing__addon_id'

    list_filter = ('billing__addon_id',)
    search_fields = ('billing__addon__id', 'billing__addon__title', 'price_descriptor')
    list_display = ('billing', 'get_price_title')
    exclude = ('sort_order',)

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('price',)
        return self.readonly_fields + ('stripe_price_id',)


@admin.register(AddonUsage)
class AddonUsageAdmin(admin.ModelAdmin):
    list_display = ('user', 'billing', 'is_active', 'created_at', 'updated_at', 'cancelled_at')

    list_filter = ('billing__addon__title', 'is_active', 'created_at', 'updated_at', 'cancelled_at')
    date_hierarchy = 'created_at'
    readonly_fields = ('stripe_subscription_id', 'stripe_subscription_item_id')

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('user',)
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        return False
