# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin

from .models import (
    TwilioPhoneNumber,
    TwilioStep,
    TwilioUpload,
    TwilioLog,
    TwilioRecording
)

admin.site.register(TwilioPhoneNumber)
admin.site.register(TwilioStep)
admin.site.register(TwilioUpload)
admin.site.register(TwilioLog)
admin.site.register(TwilioRecording)
