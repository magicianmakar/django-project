from django import template
from django.urls import reverse

register = template.Library()

PLATFORMS = {
    'shopify': 'Shopify',
    'chq': 'CommerceHQ',
    'woo': 'WooCommerce',
    'gear': 'GearBubble',
    'gkart': 'GrooveKart',
    'bigcommerce': 'BigCommerce'
}


@register.filter
def display_platform(platform):
    return PLATFORMS.get(platform)


@register.filter
def product_platform(product):
    name = product.__class__.__name__

    if name == 'ShopifyProduct':
        return 'shopify'
    elif name == 'CommerceHQProduct':
        return 'chq'
    elif name == 'WooProduct':
        return 'woo'
    elif name == 'BigCommerceProduct':
        return 'bigcommerce'
    elif name == 'GrooveKartProduct':
        return 'gkart'
    else:
        raise NotImplementedError()


@register.filter
def product_url(product):
    name = product.__class__.__name__

    if name == 'ShopifyProduct':
        return reverse('product_view', kwargs={'pid': product.id})
    elif name == 'CommerceHQProduct':
        return reverse('chq:product_detail', kwargs={'pk': product.id})
    elif name == 'WooProduct':
        return reverse('woo:product_detail', kwargs={'pk': product.id})
    elif name == 'BigCommerceProduct':
        return reverse('bigcommerce:product_detail', kwargs={'pk': product.id})
    elif name == 'GrooveKartProduct':
        return reverse('gkart:product_detail', kwargs={'pk': product.id})
    else:
        raise NotImplementedError()


@register.filter
def product_image(product):
    name = product.__class__.__name__
    images = []

    if name == 'ShopifyProduct':
        images = product.get_images()
    elif name == 'CommerceHQProduct':
        images = [product.get_image()]
    elif name == 'WooProduct':
        images = product.parsed.get('images')
    elif name == 'BigCommerceProduct':
        images = product.parsed.get('images')
    elif name == 'GrooveKartProduct':
        if product.is_connected:
            images = [product.parsed.get('cover_image')]
        else:
            images = product.parsed.get('images')
    else:
        raise NotImplementedError()

    if images:
        return images[0]
