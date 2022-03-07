from django.template.defaultfilters import slugify

from aliexpress_core.aliexpress_api import APIRequest
from aliexpress_core.models import AliexpressCategory
from lib.exceptions import capture_exception
from shopified_core.commands import DropifiedBaseCommand


class Command(DropifiedBaseCommand):
    help = 'Add/Update AliExpress Products Categories'

    def start_command(self, *args, **options):
        api = APIRequest(None)

        try:
            result = api.get_aliexpress_categories()
            api_categories = result['result']['categories']
        except Exception:
            capture_exception()
        else:
            for entry in api_categories['category']:
                category_id = str(entry['category_id'])
                category, created = AliexpressCategory.objects.update_or_create(
                    name=entry['category_name'],
                    aliexpress_id=category_id,
                )
                category.slug = slugify(entry['category_name'])
                category.description = entry['category_name']

                if 'parent_category_id' in entry.keys():
                    parent_category = AliexpressCategory.objects.get(
                        aliexpress_id=entry['parent_category_id']
                    )
                    category.parent = parent_category

                # Hide categories
                if category_id in ['2', '3', '201520802', '200001075', '201169612']:
                    category.is_hidden = True

                # Rename categories
                if category_id == '201768104':
                    category.description = 'Sportswear'
                if category_id == '21':
                    category.description = 'Craft & Stationery'
                if category_id == '509':
                    category.description = 'Phones and Accessories'
                if category_id == '1501':
                    category.description = 'Mother & Baby'
                if category_id == '1420':
                    category.description = 'DIY & Tools'
                if category_id == '34':
                    category.description = 'Car Parts & Accessories'
                if category_id == '200000532':
                    category.description = 'Novelty Costumes'

                category.save()
