# -*- coding:utf8 -*-

from django.contrib import admin
from article.models import *


class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'stat', 'views', 'created_at', 'updated_at',)
    list_filter = ('stat',)
    date_hierarchy = 'created_at'
    ordering = ('created_at', 'updated_at', 'stat')
    search_fields = ('title', 'body')
    raw_id_fields = ('author',)

    # Configuration du formulaire d'edition
    fieldsets = (
        # Fieldset
        ('General', {
            #'classes': ['collapse',],
            'fields': ('title', 'author', 'slug', 'stat', 'body_format')
        }),
        # Fieldset
        ('Page content', {
            'description':'HTML tags are accepeted',
            'fields': ('body', )
        }),
        ('Page Style', {
            'description':'CSS Style of this page',
            'fields': ('style', )
        }),
    )

    def view_on_site(self, obj):
        return '/pages/{}'.format(obj.slug)

class CommentAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'stat', 'created_at', 'updated_at',)
    list_filter = ('stat', 'author')
    date_hierarchy = 'created_at'
    ordering = ('created_at', 'updated_at', 'stat')
    search_fields = ('title', 'body')
    raw_id_fields = ('author', 'article')

    # Configuration du formulaire d'edition
    fieldsets = (
        # Fieldset
        ('General', {
            #'classes': ['collapse',],
            'fields': ('title', 'author', 'stat', 'article', 'parent')
        }),
        # Fieldset
        ('Blog content', {
            'description':'HTML tags are accepeted',
            'fields': ('body', )
        }),
    )


class SidebarLinkAdmin(admin.ModelAdmin):
    list_display = ('title', 'order', 'link')
    search_fields = ('title', 'link')
    filter_horizontal = ('display_plans',)


admin.site.register(Article, ArticleAdmin)
admin.site.register(ArticleTag)
admin.site.register(SidebarLink, SidebarLinkAdmin)
