from django.db import models

from django.contrib.auth.models import User
from django.template import Context, Template

from app.lsapi import lsapi

import requests, urllib2

from app.settings import CRAWLER_API_BASE, CRAWLER_API_CALLBACK_BASE

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
        moz_metrics = {
            'api_mozrank_url': 'N/A',
            'api_domain_authority': 'N/A',
            'api_external_equity_links': 'N/A',
        }

        google_metrics = {
            'api_google_speed_score': 'N/A',
            'api_google_speed_report_url': 'N/A',
        }

        sharecount_metrics = {
            'api_sharecount_facebook':  'N/A',
            'api_sharecount_googleplus': 'N/A',
            'api_sharecount_twitter':   'N/A',
            'api_sharecount_linkedin':  'N/A',
            'api_sharecount_pinterest': 'N/A',
        }

        crawler_metrics = {
            'api_crawler_links_count':  'N/A',
            'api_crawler_duplicate_descriptions':  'N/A',
            'api_crawler_duplicate_title': 'N/A',
            'api_crawler_images_missing_alt':   'N/A',
            'api_crawler_notfound_links_count': 'N/A',
        }

        user_metrics = {}
        for i in metrics:
            if i.name.startswith('api_'):
                moz_metrics[i.name] = i.value
            else:
                user_metrics[i.name] = i.value

        all_metrics = {}
        all_metrics.update(user_metrics)
        all_metrics.update(moz_metrics)
        all_metrics.update(google_metrics)
        all_metrics.update(sharecount_metrics)
        all_metrics.update(crawler_metrics)


        if mtype == 'all':
            return all_metrics

        if mtype == 'moz':
            return moz_metrics

        if mtype == 'google':
            return google_metrics

        if mtype == 'sharecount':
            return sharecount_metrics

        if mtype == 'crawler':
            return crawler_metrics

        if mtype == 'user':
            return user_metrics

    def update_api_metrics(self, only=None):
        if not only or only in ['api_mozrank_url', 'api_domain_authority', 'api_external_equity_links']:
            l = lsapi('mozscape-5a9d3a64d9', 'e4d61017b456062ddbf8b995b818a3ba')
            metrics = l.urlMetrics(self.url)

        if not only or only == 'api_mozrank_url':
            try:
                m = self.metric_set.get(name='api_mozrank_url')
            except:
                m = Metric(name='api_mozrank_url', description='MozRank: URL', project=self)

            m.value = metrics['umrp']
            m.save()

        if not only or only == 'api_domain_authority':
            try:
                m = self.metric_set.get(name='api_domain_authority')
            except:
                m = Metric(name='api_domain_authority', description='Domain Authority', project=self)

            m.value = metrics['pda']
            m.save()

        if not only or only == 'api_external_equity_links':
            try:
                m = self.metric_set.get(name='api_external_equity_links')
            except:
                m = Metric(name='api_external_equity_links', description='External Equity Links', project=self)

            m.value = metrics['ueid']
            m.save()

        if not only or only == 'api_google_speed_score':

            response = requests.get(
                url='https://www.googleapis.com/pagespeedonline/v1/runPagespeed',
                params={
                    'url': self.url,
                    'key': 'AIzaSyAJc6rUtNc0J1GMePCjLSggnWiKJmTYxj4'
                }
            )

            try:
                m = self.metric_set.get(name='api_google_speed_score')
            except:
                m = Metric(name='api_google_speed_score', description='Google Speed Test Score', project=self)

            m.value = response.json().get('score')
            m.save()

        if not only or only == 'api_google_speed_report_url':
            try:
                m = self.metric_set.get(name='api_google_speed_report_url')
            except:
                m = Metric(name='api_google_speed_report_url', description='Google Speed Test Report URL', project=self)

            m.value = 'https://developers.google.com/speed/pagespeed/insights/?url=%s&tab=desktop'%urllib2.quote(self.url)
            m.save()

        if not only or only in ['api_sharecount_facebook', 'api_sharecount_googleplus', 'api_sharecount_twitter',
                                'api_sharecount_linkedin', 'api_sharecount_pinterest']:
            response = requests.get(
                url='https://free.sharedcount.com/url',
                params={
                    'url': self.url,
                    'apikey': '4a7df4081d5ab4671e31872f1cffc71318f896a4'
                }
            ).json()

        if not only or only == 'api_sharecount_facebook':
            try:
                m = self.metric_set.get(name='api_sharecount_facebook')
            except:
                m = Metric(name='api_sharecount_facebook', description='Facebook Share Count', project=self)

            m.value = response.get('Facebook').get('share_count')
            m.save()

        if not only or only == 'api_sharecount_googleplus':
            try:
                m = self.metric_set.get(name='api_sharecount_googleplus')
            except:
                m = Metric(name='api_sharecount_googleplus', description='Google+ Share Count', project=self)

            m.value = response.get('GooglePlusOne')
            m.save()

        if not only or only == 'api_sharecount_twitter':
            try:
                m = self.metric_set.get(name='api_sharecount_twitter')
            except:
                m = Metric(name='api_sharecount_twitter', description='Twitter Share Count', project=self)

            m.value = response.get('Twitter')
            m.save()

        if not only or only == 'api_sharecount_linkedin':
            try:
                m = self.metric_set.get(name='api_sharecount_linkedin')
            except:
                m = Metric(name='api_sharecount_linkedin', description='LinkedIn Share Count', project=self)

            m.value = response.get('LinkedIn')
            m.save()

        if not only or only == 'api_sharecount_pinterest':
            try:
                m = self.metric_set.get(name='api_sharecount_pinterest')
            except:
                m = Metric(name='api_sharecount_pinterest', description='Pinterest Share Count', project=self)

            m.value = response.get('Pinterest')
            m.save()


        if only == 'api_crawler':
            requests.get('%s/crawl'%CRAWLER_API_BASE,{
                'name': self.title,
                'url': self.url.rstrip('/'),
                'callback': '%s/project/metrics/%d?crawler={TASK_ID}'%(CRAWLER_API_CALLBACK_BASE, self.id)
            })

    def update_crawler_metrics(self, task_id):
        rep = requests.get('%s/get'%CRAWLER_API_BASE, {'id': task_id})
        data = rep.json()

        data_map = {
            'api_crawler_links_count':  {
                'name': 'links_count',
                'info': 'Total links count'
            },
            'api_crawler_duplicate_descriptions':  {
                'name': 'duplicate_descriptions',
                'info': 'Pages with the same description'
            },
            'api_crawler_duplicate_title': {
                'name': 'duplicate_title',
                'info': 'Pages with the same title'
            },
            'api_crawler_images_missing_alt':   {
                'name': 'images_missing_alt',
                'info': 'Images messing alt tag'
            },
            'api_crawler_notfound_links_count': {
                'name': 'notfound_links_count',
                'info': '404 links count'
            }
        }

        for key in data_map:
            try:
                m = self.metric_set.get(name=key)
            except:
                m = Metric(name=key, description=data_map[key]['info'], project=self)

            m.value = data.get(data_map[key]['name'])
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