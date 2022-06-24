from bigcommerce_core.models import BigCommerceOrderTrack, BigCommerceProduct, BigCommerceStore, BigCommerceSupplier, BigCommerceUserUpload
from commercehq_core.models import CommerceHQOrderTrack, CommerceHQProduct, CommerceHQStore, CommerceHQSupplier, CommerceHQUserUpload
from ebay_core.models import EbayOrderTrack, EbayProduct, EbayStore, EbaySupplier, EbayUserUpload
from facebook_core.models import FBOrderTrack, FBProduct, FBStore, FBSupplier, FBUserUpload
from google_core.models import GoogleOrderTrack, GoogleProduct, GoogleStore, GoogleSupplier, GoogleUserUpload
from groovekart_core.models import GrooveKartOrderTrack, GrooveKartProduct, GrooveKartStore, GrooveKartSupplier, GrooveKartUserUpload
from leadgalaxy.models import ProductSupplier, ShopifyOrderTrack, ShopifyProduct, ShopifyStore, UserUpload
from my_basket.models import BasketOrderTrack
from supplements.utils.basket import BasketStore
from woocommerce_core.models import WooOrderTrack, WooProduct, WooStore, WooSupplier, WooUserUpload


def get_track_model(store_type=''):
    if store_type in ['chq', 'CommerceHQOrderTrack']:
        return CommerceHQOrderTrack
    elif store_type in ['woo', 'WooOrderTrack']:
        return WooOrderTrack
    elif store_type in ['ebay', 'EbayOrderTrack']:
        return EbayOrderTrack
    elif store_type in ['fb', 'FBOrderTrack']:
        return FBOrderTrack
    elif store_type in ['google', 'GoogleOrderTrack']:
        return GoogleOrderTrack
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
    elif store_type in ['ebay', 'EbayStore']:
        return EbayStore
    elif store_type in ['fb', 'FBStore']:
        return FBStore
    elif store_type in ['google', 'GoogleStore']:
        return GoogleStore
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
    elif store_type in ['ebay', 'EbayProduct']:
        return EbayProduct
    elif store_type in ['fb', 'FBProduct']:
        return FBProduct
    elif store_type in ['google', 'GoogleProduct']:
        return GoogleProduct
    elif store_type in ['gkart', 'GrooveKartProduct']:
        return GrooveKartProduct
    elif store_type in ['bigcommerce', 'BigCommerceProduct']:
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
    elif store_type in ['ebay', 'EbaySupplier']:
        return EbaySupplier
    elif store_type in ['fb', 'FBSupplier']:
        return FBSupplier
    elif store_type in ['google', 'GoogleSupplier']:
        return GoogleSupplier
    elif store_type in ['gkart', 'GrooveKartSupplier']:
        return GrooveKartSupplier
    elif store_type in ['bigcommerce', 'BigCommerceSupplier']:
        return BigCommerceSupplier
    else:
        return ProductSupplier


def get_user_upload_model(store_type):
    if store_type in ['chq']:
        return CommerceHQUserUpload
    elif store_type in ['woo']:
        return WooUserUpload
    elif store_type in ['gkart']:
        return GrooveKartUserUpload
    elif store_type in ['bigcommerce']:
        return BigCommerceUserUpload
    elif store_type in ['ebay']:
        return EbayUserUpload
    elif store_type in ['fb']:
        return FBUserUpload
    elif store_type in ['google']:
        return GoogleUserUpload
    else:
        return UserUpload
