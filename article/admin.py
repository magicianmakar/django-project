from article.models import Article, ArticleTag, Comment, CommentVote, SidebarLink
from django.contrib import admin


class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'stat', 'views', 'created_at', 'updated_at',)
    list_filter = ('stat',)
    date_hierarchy = 'created_at'
    ordering = ('created_at', 'updated_at', 'stat')
    search_fields = ('title', 'body')
    raw_id_fields = ('author',)

    fieldsets = (
        ('General', {
            'fields': ('title', 'author', 'slug', 'stat', 'body_format')
        }),
        ('Page content', {
            'description': 'HTML tags are accepeted',
            'fields': ('body', )
        }),
        ('Page Style', {
            'description': 'CSS Style of this page',
            'fields': ('style', )
        }),
    )

    def view_on_site(self, obj):
        return '/pages/{}'.format(obj.slug)


class SidebarLinkAdmin(admin.ModelAdmin):
    list_display = ('title', 'order', 'link')
    search_fields = ('title', 'link')
    filter_horizontal = ('display_plans',)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'body',
        'votes',
        'stat',
        'parent',
        'created_at',
        'updated_at',
        'author',
        'article',
    )
    list_filter = ('created_at', 'updated_at')
    raw_id_fields = ('author', 'article')
    date_hierarchy = 'created_at'


@admin.register(CommentVote)
class CommentVoteAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'article',
        'comment',
        'user',
        'created_at',
        'vote_value',
    )
    list_filter = ('created_at',)
    raw_id_fields = ('article', 'comment', 'user')
    date_hierarchy = 'created_at'


admin.site.register(Article, ArticleAdmin)
admin.site.register(ArticleTag)
admin.site.register(SidebarLink, SidebarLinkAdmin)
