# -*- coding:utf8 -*-

from django.contrib import admin
from article.models import *


class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'stat', 'created_at', 'updated_at',)
    list_filter = ('stat', 'author')
    date_hierarchy = 'created_at'
    ordering = ('created_at', 'updated_at', 'stat')
    search_fields = ('title', 'body')
    raw_id_fields = ('author',)

    # Configuration du formulaire d'edition
    fieldsets = (
        # Fieldset
        ('General', {
            #'classes': ['collapse',],
            'fields': ('title', 'author', 'slug', 'stat')
        }),
        # Fieldset
        ('Blog content', {
            'description':'HTML tags are accepeted',
            'fields': ('body', )
        }),
    )

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

admin.site.register(Article)
# admin.site.register(Comment, CommentAdmin)
admin.site.register(ArticleTag)
admin.site.register(SidebarLink)

