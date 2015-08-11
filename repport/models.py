from django.db import models

from django.contrib.auth.models import User
from django.template import Context, Template

BOOL_CHOICES = (
    (1, 'Yes'),
    (0, 'No'),
)

class Project(models.Model):
    title = models.CharField(max_length=512)
    website = models.CharField(max_length=256, blank=True, default='')
    url = models.CharField(max_length=256, blank=True, default='')
    logo = models.CharField(max_length=256, blank=True, default='')

    description = models.TextField(blank=True, default='')
    conclusion = models.TextField(blank=True, default='')

    template = models.ForeignKey('ProjectTemplate')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creation Date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last Update')

    def __str__(self):
        return self.title

    def overall_score(self):
        scores = [i.category_score() for i in self.categorie_set.all()]
        return (sum(scores) / float(len(scores)))

    def categories(self):
        return self.categorie_set.all().all().order_by('id')

class Categorie(models.Model):
    title = models.CharField(max_length=512)
    content_analysis = models.TextField(blank=True, default='')
    content_score = models.TextField(blank=True, default='')
    color = models.CharField(max_length=32, blank=True, default='')
    algorithm_usage = models.IntegerField(default=0)

    project = models.ForeignKey(Project)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creation Date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last Update')

    def __str__(self):
        return self.title

    def topics(self):
        return self.topic_set.all().order_by('id')

    def category_score(self):
        scores = [i.score for i in self.topic_set.all()]
        return (sum(scores) / float(len(scores)))*10.0

    def action_items(self):
        return self.topic_set.filter(action_item=1)

class Topic(models.Model):
    title = models.CharField(max_length=512)
    score = models.IntegerField(default=0)
    action_item = models.IntegerField(default=0, choices=BOOL_CHOICES)

    analysis = models.TextField(blank=True, default='')
    recommendations = models.TextField(blank=True, default='')
    guidelines = models.TextField(blank=True, default='')
    action_description = models.TextField(blank=True, default='')

    categorie = models.ForeignKey(Categorie)

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creation Date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last Update')

    def __str__(self):
        return self.title

    def get_bs_class(self):
        if self.score >= 1 and self.score <= 3:
            return "danger"
        elif self.score >= 4 and self.score <= 7:
            return "warning"
        elif self.score >= 8 and self.score <= 10:
            return "success"
        else:
            return "active"

    def get_bg_color(self):
        if self.score >= 1 and self.score <= 3:
            return "red"
        elif self.score >= 4 and self.score <= 7:
            return "yellow"
        elif self.score >= 8 and self.score <= 10:
            return "red"
        else:
            return "blue"

class ProjectTemplate(models.Model):
    title = models.CharField(max_length=512)
    report_template = models.TextField(blank=True, default='')
    report_style = models.TextField(blank=True, default='')

    def __str__(self):
        return '%s | %s' % (self.title, self.project_set.first())