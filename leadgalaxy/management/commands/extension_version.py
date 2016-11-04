from django.core.management.base import BaseCommand
from django.core.cache import cache


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('version', type=str, help='Extension Version')
        parser.add_argument('--required', dest='required', action='store_true', help='Version is required')

    def handle(self, *args, **options):
        self.stdout.write('Change Extension Version to: {} Required: {}'.format(
            self.style.MIGRATE_SUCCESS(options['version']), options['required']), self.style.HTTP_INFO)

        cache.set('extension_release', options['version'], timeout=3600)
        cache.set('extension_required', options['required'], timeout=3600)

        cache.persist('extension_release')
        cache.persist('extension_required')
