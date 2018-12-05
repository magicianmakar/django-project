# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import itertools

from django.db import models
from django.contrib.auth.models import User


class VideosList(models.Model):
    user = models.ForeignKey(User)
    title = models.CharField(max_length=512)
    videos = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Submission date')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Last update')

    def __unicode__(self):
        return self.title

    def get_videos(self):
        return self.videos.split(';') if self.videos else []

    def set_videos(self, videos):
        self.videos = ';'.join(videos)

    def count_videos(self):
        return len(self.get_videos())

    def add_videos(self, new_videos):
        videos = self.get_videos()
        new_videos = itertools.ifilter(lambda x: x not in videos, new_videos)
        all_videos = itertools.chain(videos, new_videos)
        self.set_videos(all_videos)

    def remove_video(self, video):
        videos = self.get_videos()
        videos.remove(video)
        self.set_videos(videos)
