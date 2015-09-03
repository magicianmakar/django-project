from django.db import models

from django.contrib.auth.models import User
from django.template import Context, Template

from app.lsapi import lsapi

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

    def get_metrics(self, mtype='all'):
        metrics = self.metric_set.all()
        api_metrics = {
            'api_mozrank_url': 'N/A',
            'api_domain_authority': 'N/A',
            'api_external_equity_links': 'N/A',
        }

        user_metrics = {}
        for i in metrics:
            if i.name.startswith('api_'):
                api_metrics[i.name] = i.value
            else:
                user_metrics[i.name] = i.value

        all_metrics = {}
        all_metrics.update(user_metrics)
        all_metrics.update(api_metrics)


        if mtype == 'all':
            return all_metrics

        if mtype == 'api':
            return api_metrics

        if mtype == 'user':
            return user_metrics

    def update_api_metrics(self):
        l = lsapi('mozscape-5a9d3a64d9', 'e4d61017b456062ddbf8b995b818a3ba')
        metrics = l.urlMetrics(self.url)

        try:
            m = self.metric_set.get(name='api_mozrank_url')
        except:
            m = Metric(name='api_mozrank_url', description='MozRank: URL', project=self)

        m.value = metrics['umrp']
        m.save()

        try:
            m = self.metric_set.get(name='api_domain_authority')
        except:
            m = Metric(name='api_domain_authority', description='Domain Authority', project=self)

        m.value = metrics['pda']
        m.save()

        try:
            m = self.metric_set.get(name='api_external_equity_links')
        except:
            m = Metric(name='api_external_equity_links', description='External Equity Links', project=self)

        m.value = metrics['ueid']
        m.save()


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

class Metric(models.Model):
    name = models.CharField(max_length=512)
    value = models.CharField(max_length=512, blank=True, default='')
    description = models.CharField(max_length=512, blank=True, default='')

    project = models.ForeignKey(Project)

    def __str__(self):
        return self.name

    def code(self):
        return '{{metrics.%s}}'%self.name