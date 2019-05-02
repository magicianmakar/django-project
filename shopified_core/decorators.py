from django.core.exceptions import PermissionDenied


def add_to_class(cls, name):
    def _decorator(*args, **kwargs):
        cls.add_to_class(name, args[0])
    return _decorator


def no_subusers(func):
    def _func(request, *args, **kwargs):
        if request.user.is_subuser:
            raise PermissionDenied('Sub-User can not access this page')
        return func(request, *args, **kwargs)
    return _func


def restrict_subuser_access(func):
    """ Prevent sub users from using an endpoint """
    def _func(request, *args, **kwargs):
        if request.user.is_subuser:
            raise PermissionDenied()
        return func(request, *args, **kwargs)
    return _func


class HasSubuserPermission:
    """Checks if the request user has a specified non-store-specific subuser permission"""
    def __init__(self, subuser_permission):
        self._subuser_permission = subuser_permission

    def __call__(self, func):
        def _func(request, *args, **kwargs):
            if not request.user.can(self._subuser_permission):
                raise PermissionDenied()
            return func(request, *args, **kwargs)
        return _func


# Weak reference
class WeakList(list):
    pass


upsell_page_permissions = WeakList()
upsell_pages = WeakList()


def use_upsell_for(permission, selected_menu):
    """
    Args
        permission: only .view permissions like orders.view, place_orders.view, etc
        selected_menu: menu string from main_nav file
    """
    if permission.endswith('.view'):
        upsell_page_permissions.append(permission)
        upsell_pages.append(selected_menu)

    def decorator(func):
        def wrapper(request, *args, **kwargs):
            use_perm = permission.replace('.view', '.use')
            if not request.user.is_subuser and not request.user.can(use_perm):
                from article.views import content, Article
                from shopified_core.utils import slugify_menu
                try:
                    slug_article = slugify_menu(selected_menu)
                    article = Article.objects.get(slug=slug_article)
                    if article.stat == 0:
                        return content(request, slug_article=slug_article)

                except Article.DoesNotExist:
                    pass

            return func(request, *args, **kwargs)
        return wrapper
    return decorator


class PlatformPermissionRequired:
    platforms = ['shopify', 'commercehq', 'woocommerce', 'gearbubble', 'groovekart']

    def __init__(self, platform):
        self._platform = platform

    def __call__(self, func):
        def _func(request, *args, **kwargs):
            if self._platform not in PlatformPermissionRequired.platforms:
                raise NotImplementedError("Platform doesn't exist")
            if not request.user.can(f'{self._platform}.use'):
                raise PermissionDenied()
            return func(request, *args, **kwargs)
        return _func
