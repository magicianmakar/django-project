from .models import SidebarLink

def sidebarlinks(request):
    return {
        'sidebar_links': SidebarLink.objects.filter(parent=None)
    }
