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

    if sidebar_links:
        temp = []

        for sidebar_link in sidebar_links:
            try:
                if 'http' not in sidebar_link.link and request.app is not "shopify":
                    sidebar_link.link = "/%s%s" % (request.app, sidebar_link.link)
            except:
                pass

            temp.append(sidebar_link)

        sidebar_links = temp

    return {'sidebar_links': sidebar_links}
