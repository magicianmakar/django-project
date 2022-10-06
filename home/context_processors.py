
def all_stores(request):
    user = request.user
    if not user.is_authenticated:
        return {}

    return {
        'user_stores': request.user.profile.get_stores(request=request),
    }
