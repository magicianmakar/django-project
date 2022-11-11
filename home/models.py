from django.db import models
from django.templatetags.static import static

from leadgalaxy.models import GroupPlan


class ApplicationMenu(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=255)
    sort_order = models.PositiveIntegerField(help_text='Sort Order', default=0)

    class Meta:
        ordering = ('sort_order',)

    def __str__(self):
        return self.title


class ExtraFieldsManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().annotate(
            menu_title=models.F('menu__title'),
        )


class ApplicationMenuItem(models.Model):
    objects = ExtraFieldsManager()

    menu = models.ForeignKey(ApplicationMenu, related_name='items', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(default='', blank=True)
    icon_url = models.URLField(default='', blank=True)
    link = models.URLField()
    sort_order = models.PositiveIntegerField(help_text='Sort Order', default=0)
    new_tab = models.BooleanField(default=True)
    plans = models.ManyToManyField(GroupPlan, blank=True, related_name='applications')
    menu_title = None
    about_link = models.URLField(default='https://www.dropified.com/dropified-apps/')

    class Meta:
        ordering = ('sort_order',)

    def __str__(self):
        return self.title

    def icon(self):
        return self.icon_url if self.icon_url else static('img/application-menu-item.png')
