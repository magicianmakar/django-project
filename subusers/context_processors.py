
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
    elif namespace == 'ebay':
        template_config = {
            'base': 'base_ebay_core.html',
            'url': {
                'namespace': 'ebay:',
                'prefix': '/ebay'
            }
        }
    elif namespace == 'fb':
        template_config = {
            'base': 'base_fb_core.html',
            'url': {
                'namespace': 'fb:',
                'prefix': '/fb'
            }
        }
    elif namespace == 'google':
        template_config = {
            'base': 'base_google_core.html',
            'url': {
                'namespace': 'google:',
                'prefix': '/google'
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
    elif namespace == 'gkart':
        template_config = {
            'base': 'base_groovekart_core.html',
            'url': {
                'namespace': 'gkart:',
                'prefix': '/gkart'
            }
        }
    elif namespace == 'bigcommerce':
        template_config = {
            'base': 'base_bigcommerce_core.html',
            'url': {
                'namespace': 'bigcommerce:',
                'prefix': '/bigcommerce'
            }
        }
    elif namespace == 'fb_marketplace':
        template_config = {
            'base': 'base_fb_marketplace_core.html',
            'url': {
                'namespace': 'fb_marketplace:',
                'prefix': '/fb_marketplace'
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
