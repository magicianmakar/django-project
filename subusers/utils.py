
def get_namespace(request):
    try:
        return request.resolver_match.namespaces[0] + ':'
    except:
        return ''
