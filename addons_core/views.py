from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, ListView
from django.views.generic.detail import BaseDetailView
from django.views.generic.list import BaseListView
from django.shortcuts import get_object_or_404

from addons_core.models import Addon, Category


class BaseTemplateView(TemplateView):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['addon_category'] = Category.objects.all().filter(is_visible=True)
        ctx['user_addons'] = [i.id for i in self.request.user.profile.addons.all()]
        return ctx


class AddonsListView(BaseListView, BaseTemplateView):
    model = Addon
    template_name = 'addons/addons_list.html'

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
        ctx['breadcrumbs'] = ['Addons']

        return ctx


class AddonsDetailsView(BaseDetailView, BaseTemplateView):
    model = Addon
    template_name = 'addons/addons_details.html'

    def get_context_data(self, **kwargs: dict) -> dict:
        ctx = super().get_context_data(**kwargs)
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
        ctx['category'] = get_object_or_404(Category, slug=self.kwargs.get('slug'), is_visible=True)

        return ctx
