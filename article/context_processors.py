from django.db.models import Q, Prefetch

from .models import SidebarLink


def sidebarlinks(request):
    sidebar_links = SidebarLink.objects.filter(parent=None)
    if hasattr(request.user, 'is_subuser') and request.user.is_subuser:
        if request.user.can('view_help_and_support.sub'):
            if not request.user.can('view_bonus_training.sub'):
                queryset = SidebarLink.objects.exclude(title__icontains='Bonus Training')
                sidebar_links = sidebar_links.prefetch_related(Prefetch('childs', queryset=queryset))
        else:
            sidebar_links = sidebar_links.exclude(Q(title__icontains='Help & Training') |
                                                  Q(title__icontains='Support'))

    return {'sidebar_links': sidebar_links}
