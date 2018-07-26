
def template_config(request):
    try:
        namespace = request.resolver_match.namespaces[0]
    except:
        namespace = ''

    if namespace == 'chq':
        template_config = {
            'base': 'base_commercehq_core.html',
            'url': {
                'namespace': 'chq:',
                'prefix': '/chq'
            }
        }
    elif namespace == 'woo':
        template_config = {
            'base': 'base_woocommerce_core.html',
            'url': {
                'namespace': 'woo:',
                'prefix': '/woo'
            }
        }
    elif namespace == 'gear':
        template_config = {
            'base': 'base_gearbubble_core.html',
            'url': {
                'namespace': 'gear:',
                'prefix': '/gear'
            }
        }
    else:
        template_config = {
            'base': 'base.html',
            'url': {
                'namespace': '',
                'prefix': ''
            }
        }

    return {
        'template_config': template_config
    }
