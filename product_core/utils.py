from shopified_core.models import ProductBase
from shopified_core.models_utils import get_product_model

from shopified_core.utils import safe_str
from shopify_orders.utils import get_elastic


def format_model_id(model, model_id=None, model_name=None):
    if model_id is None:
        model_id = model.id

    if model_name is None:
        model_name = model.__class__.__name__

    return f'{model_name}:{model_id}'.lower()


def get_product_from_hit(hit):
    return get_product_model(hit.platform).objects.get(id=hit.meta.id.split(':').pop())


def format_body(product: ProductBase, platform: str):
    return {
        "store": product.store_id,
        "user": product.user_id,
        "platform": platform,

        "source_id": product.source_id,

        "title": product.title,
        "price": product.price,
        "product_type": safe_str(product.product_type),

        "tags": safe_str(product.tags).split(','),
        "boards": product.boards_list or [],

        "created_at": product.created_at,
        "updated_at": product.updated_at,
    }


def get_dataset(product: ProductBase, platform: str):
    return {
        "_index": "products-index",
        "_type": "product",
        "_id": format_model_id(product),
        "_source": format_body(product, platform)
    }


def update_product_es(product: ProductBase, platform: str):
    es = get_elastic()

    if es:
        es.index(
            index="products-index",
            doc_type="product",
            id=format_model_id(product),
            body=format_body(product, platform)
        )


def delete_product_es(product_id, platform):
    es = get_elastic()

    if es:
        es.delete(
            index="products-index",
            doc_type="product",
            id=format_model_id(None, product_id, platform)
        )
