from bleach import clean

from django.contrib.auth.models import User
from django.db import models
from django.template.defaultfilters import slugify

from leadgalaxy.models import GroupPlan, FeatureBundle

PUBLISH_STAT = (
    (0, 'Published'),
    (1, 'Draft'),
    (2, 'Waitting review'),
)

ARTICLE_FORMAT = (
    ('wysiwyg', 'WYSIWYG'),
    ('markdown', 'Markdown'),
)

STORE_TYPES = (
    ('default', 'All Stores'),
    ('shopify', 'Shopify'),
    ('chq', 'CommerceHQ'),
    ('woo', 'WooCommerce'),
    ('gkart', 'GrooveKart'),
    ('bigcommerce', 'BigCommerce'),
    ('ebay', 'eBay'),
    ('fb', 'Facebook'),
    ('google', 'Google'),
)


class Article(models.Model):

    class Meta:
        verbose_name = "Page"
        verbose_name_plural = "Pages"

    title = models.CharField(max_length=140)
    slug = models.CharField(max_length=140)
    body = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    stat = models.IntegerField(choices=PUBLISH_STAT, default=0, verbose_name='Publish stat')
    tags = models.ManyToManyField('ArticleTag', blank=True)
    views = models.IntegerField(default=0)
    style = models.TextField(blank=True, null=True)
    body_format = models.CharField(choices=ARTICLE_FORMAT, max_length=64, default='wysiwyg', verbose_name='Article format')

    show_header = models.BooleanField(default=True, verbose_name='Show Page Title')
    show_sidebar = models.BooleanField(default=True)
    show_searchbar = models.BooleanField(default=True)
    show_breadcrumb = models.BooleanField(default=True)

    candu_slug = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __str__(self):
        return self.title

    def get_status(self):
        return PUBLISH_STAT[int(self.stat)][1]

    def text_title(self):
        return clean(self.title, tags=[], strip=True).strip()

    def save(self, **kwargs):
        if not self.slug:
            slug = slugify(self.title)
            while True:
                try:
                    article = Article.objects.get(slug=slug)
                    if article == self:
                        self.slug = slug
                        break
                    else:
                        slug = slug + '-'
                except:
                    self.slug = slug
                    break

        super(Article, self).save()


class ArticleTag(models.Model):

    class Meta:
        verbose_name = "Page Tag"
        verbose_name_plural = "Page Tags"

    title = models.CharField(unique=True, max_length=50)
    index = models.IntegerField(default=0)

    def formated(self):
        return self.title.replace('-', ' ').replace('_', ' ').title()

    def get_link(self):
        return '/pages/tagged/{}'.format(self.title.replace(' ', '-').lower())

    def __str__(self):
        return self.title


class SidebarLink(models.Model):

    class Meta:
        verbose_name = "Sidebar Link"
        verbose_name_plural = "Sidebar Links"
        ordering = ['-order', 'title']

    title = models.CharField(max_length=100)
    slug = models.CharField(max_length=100, blank=True, null=True)
    link = models.CharField(max_length=512)
    badge = models.CharField(blank=True, default='', max_length=20)
    order = models.IntegerField(default=0)
    new_tab = models.BooleanField(default=False)
    icon = models.CharField(blank=True, default='', max_length=512)
    inherit_plan = models.BooleanField(default=False, verbose_name='Show For Subuser If Parent Can See It')

    parent = models.ForeignKey('SidebarLink', on_delete=models.SET_NULL, related_name='childs', blank=True, null=True)
    store_type = models.CharField(choices=STORE_TYPES, max_length=50, default='default')

    display_plans = models.ManyToManyField(GroupPlan, blank=True)
    display_bundles = models.ManyToManyField(FeatureBundle, blank=True)

    def __str__(self):
        return self.title

    def plans(self):
        return self.display_plans.values_list('register_hash', flat=True)


class Comment(models.Model):
    title = models.CharField(max_length=140)
    body = models.TextField()
    votes = models.IntegerField(default=0)
    stat = models.IntegerField(choices=PUBLISH_STAT, default=0, verbose_name='Publish stat')

    parent = models.IntegerField(default=0, verbose_name='Parent comment')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submittion date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    author = models.ForeignKey(User, on_delete=models.CASCADE)
    article = models.ForeignKey(Article, on_delete=models.CASCADE)

    def __str__(self):
        return self.title


class CommentVote(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Vote date')
    vote_value = models.IntegerField(verbose_name='Vore Value')

    def __str__(self):
        return "%s: %s" % (('Up' if self.vote_value > 0 else 'Down'), self.article.title)
