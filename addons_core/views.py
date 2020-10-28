from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import ListView, TemplateView
from django.views.generic.detail import BaseDetailView
from django.views.generic.list import BaseListView

from addons_core.models import Addon, Category
from urllib.parse import quote_plus, unquote_plus
from shopified_core import permissions
import simplejson as json


class BaseTemplateView(TemplateView):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['addon_category'] = Category.objects.all().filter(is_visible=True)
        ctx['user_addons'] = self.request.user.models_user.profile.addons.all()
        ctx['user_addon_ids'] = [i.id for i in ctx['user_addons']]

        return ctx


class AddonsListView(BaseListView, BaseTemplateView):
    model = Addon
    template_name = 'addons/addons_list.html'

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['breadcrumbs'] = ['Addons']
        title = self.request.GET.get('title', None)
        if title:
            ctx['search'] = True
            ctx['search_results'] = ctx['object_list'].filter(
                Q(title__icontains=title)
                | Q(slug__icontains=title),
                hidden=False
            )

        return ctx


class AddonsDetailsView(BaseDetailView, BaseTemplateView):
    model = Addon
    template_name = 'addons/addons_details.html'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.slug != kwargs.get('slug'):
            return redirect('addons.details_view',
                            permanent=True,
                            pk=self.object.id,
                            slug=self.object.slug)

        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        try:
            return self.object
        except AttributeError:
            return super().get_object(queryset)

    def get_context_data(self, **kwargs: dict) -> dict:
        permission_count = 0
        for p in self.object.permissions.all():
            if self.request.user.can(p.name):
                permission_count += 1
        ctx = super().get_context_data(**kwargs)
        ctx['permission_count'] = permission_count

        ctx['breadcrumbs'] = [
            {
                'title': 'Addons',
                'url': reverse('addons.list_view')
            },
            self.object.title
        ]

        return ctx


class AddonsEditView(BaseDetailView, BaseTemplateView):
    model = Addon
    template_name = 'addons/addons_edit.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if request.user.can('addons_edit.use'):
            return super().dispatch(request, *args, **kwargs)
        else:
            raise permissions.PermissionDenied()

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['breadcrumbs'] = [
            {
                'title': 'Addons',
                'url': reverse('addons.list_view')
            },
            'Edit',
            self.object.title
        ]

        return ctx


class MyAddonsListView(BaseTemplateView):
    template_name = 'addons/myaddons_list.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['breadcrumbs'] = ['My Addons']

        len_addons = len(ctx['user_addon_ids'])
        if len_addons == 1:
            ctx['my_addons_count'] = '1 Addon'
        else:
            ctx['my_addons_count'] = f'{len_addons} Addons'

        return ctx


class CategoryListView(ListView):
    model = Addon
    template_name = 'addons/addons_category.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        slug = self.kwargs.get('slug')
        qs = qs.filter(categories__slug=slug).exclude(hidden=True)
        return qs

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        slug = self.kwargs.get('slug')
        ctx['category'] = get_object_or_404(Category, slug=slug, is_visible=True)
        ctx['breadcrumbs'] = [
            {
                'title': 'Category',
                'url': reverse('addons.category_view', kwargs={'slug': slug})
            }
        ]

        return ctx


class UpsellInstall(BaseDetailView, TemplateView):
    model = Addon
    template_name = 'addons/upsell_install.html'

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        try:
            drop_addons_upsells = json.loads(unquote_plus(request.COOKIES.get('drop-addons-upsells')))
        except:
            drop_addons_upsells = {}

        drop_addons_upsells[self.object.slug] = {"slug": self.object.slug, "id": self.object.id}
        response.set_cookie('drop-addons-upsells', quote_plus(json.dumps(drop_addons_upsells, separators=(',', ':'))))
        return response

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        return ctx


@method_decorator(login_required, name='dispatch')
class UpsellInstallLoggedIn(BaseDetailView, TemplateView):
    model = Addon
    template_name = 'addons/upsell_install_loggedin.html'
