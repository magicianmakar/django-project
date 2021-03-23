from bigcommerce_core.models import BigCommerceOrderTrack, BigCommerceProduct, BigCommerceStore, BigCommerceSupplier
from commercehq_core.models import CommerceHQOrderTrack, CommerceHQProduct, CommerceHQStore, CommerceHQSupplier
from groovekart_core.models import GrooveKartOrderTrack, GrooveKartProduct, GrooveKartStore, GrooveKartSupplier
from leadgalaxy.models import ShopifyOrderTrack, ShopifyProduct, ShopifyStore, ProductSupplier
from my_basket.models import BasketOrderTrack
from supplements.utils.basket import BasketStore
from woocommerce_core.models import WooOrderTrack, WooProduct, WooStore, WooSupplier


def get_track_model(store_type=''):
    if store_type in ['chq', 'CommerceHQOrderTrack']:
        return CommerceHQOrderTrack
    elif store_type in ['woo', 'WooOrderTrack']:
        return WooOrderTrack
    elif store_type in ['gkart', 'GrooveKartOrderTrack']:
        return GrooveKartOrderTrack
    elif store_type in ['bigcommerce', 'BigCommerceOrderTrack']:
        return BigCommerceOrderTrack
    elif store_type in ['mybasket', 'BasketOrderTrack']:
        return BasketOrderTrack
    else:
        return ShopifyOrderTrack


def get_store_model(store_type=''):
    if store_type in ['chq', 'CommerceHQStore']:
        return CommerceHQStore
    elif store_type in ['woo', 'WooStore']:
        return WooStore
    elif store_type in ['gkart', 'GrooveKartStore']:
        return GrooveKartStore
    elif store_type in ['bigcommerce', 'BigCommerceStore']:
        return BigCommerceStore
    elif store_type in ['mybasket']:
        return BasketStore
    else:
        return ShopifyStore


def get_product_model(store_type):
    if store_type in ['chq', 'CommerceHQProduct']:
        return CommerceHQProduct
    elif store_type in ['woo', 'WooProduct']:
        return WooProduct
    elif store_type in ['gkart', 'GrooveKartProduct']:
        return GrooveKartProduct
    elif store_type in ['bigcommerce', 'BigCommerceStore']:
        return BigCommerceProduct
    elif store_type in ['mybasket']:
        return BasketStore
    else:
        return ShopifyProduct


def get_supplier_model(store_type):
    if store_type in ['chq', 'CommerceHQSupplier']:
        return CommerceHQSupplier
    elif store_type in ['woo', 'WooSupplier']:
        return WooSupplier
    elif store_type in ['gkart', 'GrooveKartSupplier']:
        return GrooveKartSupplier
    elif store_type in ['bigcommerce', 'BigCommerceSupplier']:
        return BigCommerceSupplier
    else:
        return ProductSupplier
