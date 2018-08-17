from .models import Event


def analytic_events(request):
    if not request.user.is_anonymous:
        events = Event.objects.filter(user=request.user).order_by('created_at')
        if events:
            return {'analytic_events': events}
    return {}
