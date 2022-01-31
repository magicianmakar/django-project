from adminsortable2.admin import SortableAdminMixin
from django.contrib import admin

from addons_core.admin import FormWithRequestMixin
from home.forms import ApplicationMenuItemForm
from home.models import ApplicationMenu, ApplicationMenuItem


@admin.register(ApplicationMenu)
class ApplicationMenuAdmin(SortableAdminMixin, admin.ModelAdmin):
    prepopulated_fields = {'slug': ('title',)}
    search_fields = ('slug', 'title')
    exclude = ('sort_order',)


@admin.register(ApplicationMenuItem)
class ApplicationMenuItemAdmin(SortableAdminMixin, FormWithRequestMixin, admin.ModelAdmin):
    form = ApplicationMenuItemForm

    list_display = ('title', 'menu_title')
    search_fields = ('title', 'description', 'link', 'menu__title')
    exclude = ('sort_order',)
    filter_horizontal = ('plans',)
