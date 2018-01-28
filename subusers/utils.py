
def get_namespace(request):
    try:
        request.resolver_match.view_name.split(':')[0]
    except:
        return ''
