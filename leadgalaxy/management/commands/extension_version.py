from django.core.management.base import BaseCommand
from django.core.cache import cache


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('version', type=str, help='Extension Version')
        parser.add_argument('--required', dest='required', action='store_true', help='Version is required')
        parser.add_argument('--min', dest='min', action='store_true', help='Version is the Minimum version')

    def handle(self, *args, **options):
        cache.set('extension_release', options['version'], timeout=3600)
        cache.set('extension_required', options['required'], timeout=3600)

        if options['min']:
            cache.set('extension_min_version', options['version'], timeout=3600)
            cache.persist('extension_min_version')

        cache.persist('extension_release')
        cache.persist('extension_required')

        self.stdout.write('Minimum Version: {}'.format(
            self.style.MIGRATE_SUCCESS(cache.get('extension_min_version'))), self.style.HTTP_INFO)

        self.stdout.write('Latest Version: {}'.format(
            self.style.MIGRATE_SUCCESS(cache.get('extension_release'))), self.style.HTTP_INFO)

        self.stdout.write('      Required: {}'.format(
            self.style.MIGRATE_SUCCESS(cache.get('extension_required'))), self.style.HTTP_INFO)
