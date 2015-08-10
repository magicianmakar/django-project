from django.contrib import admin
from .models import *

class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'website', 'created_at', 'updated_at',)
    # list_filter = ('user',)
    # date_hierarchy = 'created_at'
    ordering = ('created_at', 'updated_at')
    search_fields = ('title', 'description')

    # Configuration du formulaire d'edition
    fieldsets = (
        ('Project info', {
            #'classes': ['collapse',],
            'fields': ('title', 'template', 'website', 'url', 'logo',) }),
        ('Details', {
            # 'description':'Project info',
            'fields': ('description', 'conclusion')
        }),
    )

class CategorieAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_at', 'updated_at',)
    # list_filter = ('user',)
    # date_hierarchy = 'created_at'
    ordering = ('created_at', 'updated_at')
    search_fields = ('title',)

    fieldsets = (
        ('Category info', {
            #'classes': ['collapse',],
            'fields': ('title', 'project', 'algorithm_usage', 'color')
        }),
        ('Content', {
            # 'description':'Project info',
            'fields': ('content_analysis', 'content_score')
        }),
    )
class TopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_at', 'updated_at',)
    # list_filter = ('user',)
    # date_hierarchy = 'created_at'
    ordering = ('created_at', 'updated_at')
    search_fields = ('title',)

    fieldsets = (
        ('Topic info', {
            #'classes': ['collapse',],
            'fields': ('title', 'categorie', 'score', 'action_item')
        }),
        ('Content', {
            # 'description':'Project info',
            'fields': ('analysis', 'recommendations', 'guidelines', 'action_description')
        }),
    )

class TemplateAdmin(admin.ModelAdmin):
    list_display = ('title',)
    # list_filter = ('user',)
    # date_hierarchy = 'created_at'
    # ordering = ('created_at', 'updated_at')
    search_fields = ('title',)

    fieldsets = (
        ('Info', {
            #'classes': ['collapse',],
            'fields': ('title',)
        }),
        ('Templates', {
            # 'classes': ['collapse',],
            'fields': ('executive_summary', 'scorecard', 'content_analysis', 'top_action_items', 'report_template')
        }),
    )

admin.site.register(Project, ProjectAdmin)
admin.site.register(Categorie, CategorieAdmin)
admin.site.register(Topic, TopicAdmin)
admin.site.register(ProjectTemplate, TemplateAdmin)
