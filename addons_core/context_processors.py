from .models import Category


def get_active_categories(request):
    return {'active_categories': Category.objects.all().filter(is_visible=True)}
