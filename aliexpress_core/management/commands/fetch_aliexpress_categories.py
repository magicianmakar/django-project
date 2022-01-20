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
                category, created = AliexpressCategory.objects.update_or_create(
                    name=entry['category_name'],
                    aliexpress_id=entry['category_id'],
                )
                if 'parent_category_id' in entry.keys():
                    parent_category = AliexpressCategory.objects.get(
                        aliexpress_id=entry['parent_category_id']
                    )

                    category.parent = parent_category
                    category.save()
