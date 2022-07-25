import json
import time

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import models
from django.template.defaultfilters import slugify

from lib.exceptions import capture_exception
from shopified_core.utils import float_to_str, hash_url_filename, safe_float

AFFILIATE_SORT_MAP = {
    'order_count': 'LAST_VOLUME_ASC',
    '-order_count': 'LAST_VOLUME_DESC',
    'price': 'SALE_PRICE_ASC',
    '-price': 'SALE_PRICE_DESC',
}

DS_SORT_MAP = {
    'order_count': 'volumeAsc',
    '-order_count': 'volumeDesc',
    'price': 'priceAsc',
    '-price': 'priceDesc',
}


class AliexpressAccount(models.Model):
    user = models.ForeignKey(User, related_name='aliexpress_account', on_delete=models.CASCADE)

    access_token = models.TextField(default='')
    aliexpress_user_id = models.CharField(max_length=255, default='', blank=True)
    aliexpress_username = models.CharField(max_length=255, default='', blank=True)

    data = models.TextField(default='', blank=True)
    is_admitad = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.aliexpress_user_id} ({self.aliexpress_username})"

    @property
    def request(self):
        from .aliexpress_api import APIRequest
        return APIRequest(self.access_token)

    def is_session_expired(self):
        account_data = json.loads(self.data)
        expire_at = safe_float(account_data.get("expire_time"))
        current_time = safe_float(time.time() * 1000)
        aliexpress_session_expiration = False
        if expire_at - current_time < 0:
            aliexpress_session_expiration = True
        return aliexpress_session_expiration

    def get_affiliate_products(self, **kwargs):
        page = kwargs.get('page')
        category_id = kwargs.get('category_id')
        keywords = kwargs.get('keywords')
        currency = kwargs.get('currency')
        price_min = kwargs.get('price_min')
        price_max = kwargs.get('price_max')
        sort = kwargs.get('sort')

        raw = kwargs.get('raw', False)
        use_cache = kwargs.get('use_cache', True)

        products_data = {
            'total_results': 0,
            'api_products': [],
        }
        cache_key = f'aliexpress_affiliate_products_{category_id}_{page}'
        if use_cache:
            products_data = cache.get(cache_key, products_data)

        if not len(products_data['api_products']):
            try:
                params = {
                    'target_currency': currency,
                    'sort': AFFILIATE_SORT_MAP[sort],
                    'page_no': page,
                }
                if category_id:
                    params['category_ids'] = str(category_id)
                if keywords:
                    params['keywords'] = str(keywords)
                # AliExpress accepts price parameter as unit cent
                if price_min:
                    params['min_sale_price'] = int(price_min * 100)
                if price_max:
                    params['max_sale_price'] = int(price_max * 100)

                result = self.request.affiliate_products(params=params)
                if result.get('error', None):
                    return '', result

                products_data['total_results'] = result['result']['total_record_count']
                products_data['api_products'] = result['result']['products'].get('product', [])

                if use_cache and len(products_data['api_products']):
                    cache.set(cache_key, products_data, timeout=300)
            except Exception:
                capture_exception()

        formatted_products = []

        for product in products_data['api_products']:
            extra_images = [img_url for img_url in product['product_small_image_urls']['string']]
            try:
                rating = product['evaluate_rate'].strip('%')
            except KeyError:
                rating = '0'

            save_for_later = {
                'id': product['product_id'],
                'title': product['product_title'],
                'price': product['target_sale_price'],
                'compare_at_price': product['target_original_price'],
                'currency': product['target_original_price_currency'],
                'images': [product['product_main_image_url']],
                'description': '',
                'original_url': product['product_detail_url'],
                'extra_images': extra_images,
                'store': {
                    'id': product['shop_id'],
                    'name': 'AliExpress',
                    'url': product['shop_url'],
                },
                'aliexpress_category_id': product['first_level_category_id'],
                'aliexpress_category_name': product['first_level_category_name'],
                'discount': product['discount'],
                'order_count': product['lastest_volume'],
                'rating': rating,
                'details_url': product['product_detail_url'],
            }

            if raw:
                save_for_later['api'] = product

            formatted_products.append(save_for_later)

        return products_data['total_results'], formatted_products

    def get_ds_recommended_products(self, **kwargs):
        page = kwargs.get('page')
        category_id = kwargs.get('category_id')
        currency = kwargs.get('currency')
        sort = kwargs.get('sort')

        raw = kwargs.get('raw', False)
        use_cache = kwargs.get('use_cache', True)

        products_data = {
            'total_results': 0,
            'api_products': [],
        }
        cache_key = f'aliexpress_ds_recommended_products_{category_id}_{page}'
        if use_cache:
            products_data = cache.get(cache_key, products_data)

        if not len(products_data['api_products']):
            try:
                params = {
                    'feed_name': 'DS bestseller',
                    'target_currency': currency,
                    'sort': DS_SORT_MAP[sort],
                    'page_no': page,
                }
                if category_id:
                    params['category_id'] = str(category_id)

                result = self.request.ds_recommended_products(params=params)
                if result.get('error', None):
                    return '', result

                products_data['total_results'] = result['total_record_count']
                products_data['api_products'] = result['products'].get('integer', [])

                if use_cache and len(products_data['api_products']):
                    cache.set(cache_key, products_data, timeout=600)
            except:
                capture_exception()

        formatted_products = []

        for product in products_data['api_products']:
            extra_images = [img_url for img_url in product['product_small_image_urls']['string']]
            try:
                rating = product['evaluate_rate'].strip('%')
            except KeyError:
                rating = '0'

            save_for_later = {
                'id': product['product_id'],
                'title': product['product_title'],
                'price': product['target_sale_price'],
                'compare_at_price': product['target_original_price'],
                'currency': product['target_original_price_currency'],
                'images': [product['product_main_image_url']],
                'original_url': product['product_detail_url'],
                'extra_images': extra_images,
                'store': {
                    'id': product.get('shop_id'),
                    'name': 'AliExpress',
                    'url': product.get('shop_url'),
                },
                'aliexpress_category_id': product['first_level_category_id'],
                'aliexpress_category_name': product['first_level_category_name'],
                'discount': product['discount'],
                'order_count': product['lastest_volume'],
                'rating': rating,
                'details_url': product['product_detail_url'],
            }

            if raw:
                save_for_later['api'] = product

            formatted_products.append(save_for_later)

        return products_data['total_results'], formatted_products

    def get_ds_product_details(self, product_id, currency='USD', raw=False, use_cache=True):
        ds_result = {}
        ds_cache_key = f'aliexpress_ds_product_details_{product_id}_{currency}'
        affiliate_result = {}
        affiliate_cache_key = f'aliexpress_affiliate_product_details_{product_id}_{currency}'
        if use_cache:
            ds_result = cache.get(ds_cache_key, {})
            affiliate_result = cache.get(affiliate_cache_key, {})
        if not ds_result:
            params = {
                'product_id': product_id,
                'target_currency': currency,
            }
            ds_result = self.request.find_ds_product(params=params)
            if ds_result.get('error', None):
                return ds_result

            if use_cache:
                cache.set(ds_cache_key, ds_result, timeout=300)
        if not affiliate_result:
            params = {
                'product_ids': product_id,
                'target_currency': currency,
            }
            affiliate_result = self.request.find_affiliate_product(params=params)
            if affiliate_result.get('error', None):
                return affiliate_result

            if affiliate_result['result']['current_record_count'] == 0:
                return affiliate_result

            if use_cache:
                cache.set(affiliate_cache_key, affiliate_result, timeout=300)

        affiliate_product = affiliate_result['result']['products']['product'][0]

        images = ds_result['ae_multimedia_info_dto']['image_urls'].split(';')
        variant_images = {}
        variants_sku = {}
        variants = {}
        variants_info = {}
        variants_map = {}
        for variant in ds_result['ae_item_sku_info_dtos']['ae_item_sku_info_d_t_o']:
            main_variant_image = ''
            variant_values = []
            variant_skus = []
            for attr in variant.get('ae_sku_property_dtos', {}).get('ae_sku_property_d_t_o', []):
                if not variants.get(attr['sku_property_id']):
                    variants[attr['sku_property_id']] = {'title': attr['sku_property_name'], 'values': []}

                if attr['sku_property_value'] not in variants[attr['sku_property_id']]['values']:
                    variants[attr['sku_property_id']]['values'].append(attr['sku_property_value'])
                variant_values.append(attr['sku_property_value'])
                variant_skus.append(f"{attr['sku_property_id']}:{attr['property_value_id']}")
                variants_sku[attr['sku_property_value']] = f"{attr['sku_property_id']}:{attr['property_value_id']}"
                image = attr.get('sku_image')
                if image:
                    main_variant_image = main_variant_image if main_variant_image else image
                    variant_images[hash_url_filename(image)] = attr['sku_property_value']
                    images.append(image)

                if not variants_map.get(attr['sku_property_name']):
                    variants_map[attr['sku_property_name']] = {'title': attr['sku_property_name'], 'values': []}
                map = {
                    'title': attr['sku_property_value'],
                    'image': image,
                    'sku': f"{attr['sku_property_id']}:{attr['property_value_id']}",
                }
                if map not in variants_map[attr['sku_property_name']]['values']:
                    variants_map[attr['sku_property_name']]['values'].append(map)

            variant_name = ' / '.join(variant_values)
            if variant_name:
                variant_price = variant['sku_price']
                variants_info[variant_name] = {
                    'price': float_to_str(variant_price),
                    'compare_at': float_to_str(variant_price),
                    'sku': ';'.join(variant_skus),
                    'image': main_variant_image,
                }

            if raw and variant_name:
                variants_info[variant_name]['api'] = variant

        save_for_later = {
            'id': ds_result['ae_item_base_info_dto']['product_id'],
            'title': affiliate_product['product_title'],
            'price': affiliate_product['target_sale_price'],
            'compare_at_price': affiliate_product['target_original_price'],
            'description': ds_result['ae_item_base_info_dto']['detail'],
            'original_url': affiliate_product['product_detail_url'],
            'type': '',
            'tags': '',
            'vendor': '',
            'images': list(set(images)),
            'extra_images': [],
            'store': {
                'id': ds_result['ae_store_info']['store_id'],
                'name': ds_result['ae_store_info']['store_name'],
                'url': affiliate_product['shop_url']
            },
            'published': False,
            'weight': ds_result['package_info_dto']['gross_weight'],
            'weight_unit': 'g',
            'variants_images': variant_images,
            'variants_sku': variants_sku,
            'variants': list(variants.values()),
            'variants_info': variants_info,
            'variants_map': list(variants_map.values()),
        }

        if raw:
            save_for_later['api'] = {**ds_result, **affiliate_result}

        return save_for_later


class AliexpressCategory(models.Model):
    class Meta:
        ordering = ['-order']
        verbose_name_plural = 'Aliexpress Categories'

    slug = models.SlugField(max_length=255)
    name = models.CharField(max_length=255)
    aliexpress_id = models.CharField(max_length=255)
    parent = models.ForeignKey("self", null=True, blank=True,
                               related_name="child_categories", on_delete=models.CASCADE)

    description = models.CharField(max_length=512, blank=True, default='', verbose_name='Name visible to users')
    order = models.IntegerField(blank=True, null=True, verbose_name='Sort Order')
    is_hidden = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name}'

    def save(self, *args, **kwargs):
        if not self.id:
            self.slug = slugify(self.name)

        super().save(*args, **kwargs)

    @property
    def is_parent(self):
        return self.parent is None

    @classmethod
    def parent_ctaegories(cls):
        return cls.objects.filter(parent=None).exclude(is_hidden=True)
