# -*- coding: utf-8 -*-
# from __future__ import unicode_literals
import json
import mimetypes
from datetime import datetime
import datetime as dt

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.db.models import Sum
from django.utils import timezone

from raven.contrib.django.raven_compat.models import client as raven_client

from twilio.base.exceptions import TwilioRestException
from twilio.twiml.voice_response import VoiceResponse, Gather

from leadgalaxy.utils import aws_s3_upload
from shopified_core.utils import safeInt, app_link
from .models import (
    TwilioPhoneNumber,
    TwilioAutomation,
    TwilioStep,
    TwilioUpload,
    TwilioLog,
    TwilioRecording
)
from .utils import get_month_totals, get_month_limit, get_twilio_client


def JsonDatetimeConverter(o):
    if isinstance(o, datetime):
        return o.__str__()


@login_required
def index(request):
    if not request.user.can('phone_automation.use'):
        return render(request, 'upgrade.html')

    twilio_phone_number = getattr(request.user, 'twilio_phone_number', None)
    try:
        twilio_stats = {}
        twilio_logs = request.user.twilio_logs.filter(log_type='status-callback')
        latest_twilio_logs = twilio_logs[:5]
        twilio_stats['twilio_logs_total_count'] = twilio_logs.count()
        # TODO: Use Arrow date with customer's timezone request.session.get('django_timezone')
        today_twilio_logs = twilio_logs.filter(created_at__gte=timezone.now().date())
        twilio_stats['twilio_logs_today_count'] = today_twilio_logs.count()
        twilio_stats['today_total_duration'] = today_twilio_logs.aggregate(Sum('call_duration'))
        twilio_stats['total_duration'] = get_month_totals(request.user)
        twilio_stats['total_duration_month_limit'] = get_month_limit(request.user)
        twilio_stats['today_uniq_callers_count'] = today_twilio_logs.values('from_number').distinct().count()

    except:
        raven_client.captureException()
        latest_twilio_logs = []
        twilio_stats = False

    if (twilio_phone_number is None) and latest_twilio_logs == []:
        return HttpResponseRedirect(reverse('phone_automation_provision'))

    return render(request, 'phone_automation/index.html', {
        'page': 'phone_automation',
        'twilio_phone_number': twilio_phone_number,
        'twilio_logs': latest_twilio_logs,
        'twilio_stats': twilio_stats,
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'Dashboard'],
    })


@login_required
def call_logs(request):
    if not request.user.can('phone_automation.use'):
        return render(request, 'upgrade.html')

    try:
        twilio_stats = {}
        twilio_phone_number = getattr(request.user, 'twilio_phone_number', None)
        twilio_logs = request.user.twilio_logs.filter(log_type='status-callback').order_by('-created_at')

    except:
        raven_client.captureException()
        twilio_logs = []
        twilio_stats = False

    return render(request, 'phone_automation/call_logs.html', {
        'page': 'phone_automation',
        'twilio_phone_number': twilio_phone_number,
        'twilio_logs': twilio_logs,
        'twilio_stats': twilio_stats,
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'Call Logs'],
    })


@login_required
@transaction.atomic
def provision(request):
    if not request.user.can('phone_automation.use'):
        return render(request, 'upgrade.html')

    if hasattr(request.user, 'twilio_phone_number'):
        messages.error(request, 'You already have phone number set')
        return HttpResponseRedirect(reverse('phone_automation_index'))

    client = get_twilio_client()
    if request.method == 'POST':
        phone_number = request.POST.get("phone_number")

        try:
            incoming_phone_number = client.incoming_phone_numbers \
                .create(
                    phone_number=phone_number,
                    voice_url=app_link(reverse('phone_automation_call_flow')),
                    status_callback=app_link(reverse('phone_automation_status_callback'))
                )
            twilio_metadata = incoming_phone_number._properties
            twilio_metadata = json.dumps(twilio_metadata, default=JsonDatetimeConverter)

            twilio_phone_number = TwilioPhoneNumber()
            twilio_phone_number.incoming_number = phone_number
            twilio_phone_number.user_id = request.user.id
            twilio_phone_number.twilio_metadata = twilio_metadata
            twilio_phone_number.twilio_sid = incoming_phone_number.sid

            # assigning automation if exists
            automation = request.user.twilio_automations.first()
            twilio_phone_number.automation = automation
            twilio_phone_number.save()
            messages.success(request, 'Phone Number has been successfully set')
            return HttpResponseRedirect(reverse('phone_automation_index'))

        except TwilioRestException:
            raven_client.captureException()
            messages.error(request, 'Error while provisioning this phone number. Please try another one.')
            return HttpResponseRedirect(reverse('phone_automation_provision'))
    else:
        areacode = request.GET.get("areacode")
        mask = request.GET.get("mask")
        if areacode or mask:
            show_filter = True
        else:
            show_filter = False

        numbers = client.available_phone_numbers("US") \
                        .toll_free \
                        .list(voice_enabled=True, area_code=areacode, contains=mask, page_size=12)
        twilio_phone_numbers_pool = numbers

    return render(request, 'phone_automation/provision.html', {
        'page': 'phone_automation',
        'show_filter': show_filter,
        'twilio_phone_numbers_pool': twilio_phone_numbers_pool,
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'Setup Incoming Phone #'],
    })


@login_required
@transaction.atomic
def provision_release(request):
    if not request.user.can('phone_automation.use'):
        return render(request, 'upgrade.html')

    if not hasattr(request.user, 'twilio_phone_number'):
        messages.error(request, 'You do not have any phone number set')
        return HttpResponseRedirect(reverse('phone_automation_index'))

    twilio_phone_number = request.user.twilio_phone_number
    removal_avail_date = twilio_phone_number.created_at + dt.timedelta(days=30)
    if not request.user.can('phone_automation_unlimited_phone_numbers.use') and timezone.now() < removal_avail_date:
        messages.error(request, u'You can not remove this phone number until {}'.format(removal_avail_date.strftime("%b %d, %Y")))
        return HttpResponseRedirect(reverse('phone_automation_index'))

    try:
        client = get_twilio_client()
        client.incoming_phone_numbers(twilio_phone_number.twilio_sid).delete()

        twilio_phone_number.delete()

        messages.success(request, 'Phone number has been successfully removed')
        return HttpResponseRedirect(reverse('phone_automation_index'))

    except:
        raven_client.captureException()
        messages.error(request, 'Error while removing phone number. ')
        return HttpResponseRedirect(reverse('phone_automation_index'))


def save_automation(request, twilio_phone_number_id):
    twilio_phone_number = get_object_or_404(TwilioPhoneNumber, pk=twilio_phone_number_id, user=request.user)

    twilio_automation = TwilioAutomation()
    twilio_automation.user = request.user
    twilio_automation.first_step = request.POST.get('first_step')
    twilio_automation.last_step = request.POST.get('last_step')
    twilio_automation.save()

    def save_all_steps(node, parent=None):
        if node.get('step', 0) != 0:
            parent = TwilioStep.objects.create(
                automation=twilio_automation,
                parent=parent,
                block_type=node.get('block_type'),
                step=node.get('step'),
                next_step=node.get('next_step'),
                config=json.dumps(node.get('config')),
            )

        if len(node.get('children')):
            for node in node.get('children'):
                save_all_steps(node, parent)

    nodes = json.loads(request.POST.get('children'))
    save_all_steps({'children': nodes})

    # Replace old automation
    old_automation = twilio_phone_number.automation

    twilio_phone_number.automation = twilio_automation
    twilio_phone_number.save()

    if old_automation:
        old_automation.delete()

    return JsonResponse({'status': 'ok'})


def automate(request, twilio_phone_number_id):
    twilio_phone_number = get_object_or_404(TwilioPhoneNumber, pk=twilio_phone_number_id, user=request.user)

    return render(request, 'phone_automation/automate.html', {
        'twilio_phone_number': twilio_phone_number,
        'automation': twilio_phone_number.automation,
        'page': 'phone_automation',
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'Automate'],
    })


def upload(request, twilio_phone_number_id):
    twilio_phone_number = get_object_or_404(TwilioPhoneNumber, pk=twilio_phone_number_id, user=request.user)
    audio = request.FILES.get('mp3')
    step = request.POST.get('step')

    # Randomize filename in order to not overwrite an existing file
    audio_name = u'{}-{}.mp3'.format(twilio_phone_number_id, step)
    audio_name = u'uploads/u{}/phone/{}'.format(request.user.id, audio_name)
    mimetype = mimetypes.guess_type(audio.name)[0]

    upload_url = aws_s3_upload(
        filename=audio_name,
        fp=audio,
        mimetype=mimetype,
        bucket_name=settings.S3_UPLOADS_BUCKET
    )

    TwilioUpload.objects.create(
        user=request.user.models_user,
        phone=twilio_phone_number,
        url=upload_url[:510]
    )

    return JsonResponse({
        'status': 'ok',
        'url': upload_url
    })


def call_flow(request):
    phone = TwilioPhoneNumber.objects.get(incoming_number=request.POST.get('To'))
    response = VoiceResponse()

    total_duration = get_month_totals(phone.user)
    total_duration_month_limit = get_month_limit(phone.user)

    # if monthly limmit reached, reject the call
    if total_duration_month_limit and total_duration > total_duration_month_limit:
        response.reject()
    else:
        try:
            next_step = phone.automation.steps.get(step=phone.automation.first_step)
            response.redirect(next_step.url)
        except:
            raven_client.captureException()
            response.reject()

    return HttpResponse(str(response), content_type='application/xml')


def call_flow_speak(request):
    phone = TwilioPhoneNumber.objects.get(incoming_number=request.POST.get('To'))
    current_step = phone.automation.steps.get(step=request.GET.get('step'))
    config = current_step.get_config()

    response = VoiceResponse()
    if config.get('mp3'):
        response.play(config.get('mp3'))
    elif config.get('say'):
        response.say(config.get('say'), voice=config.get('voice'))

    response.redirect(current_step.redirect)
    return HttpResponse(str(response), content_type='application/xml')


def call_flow_menu(request):
    phone = TwilioPhoneNumber.objects.get(incoming_number=request.POST.get('To'))
    current_step = phone.automation.steps.get(step=request.GET.get('step'))
    config = current_step.get_config()

    response = VoiceResponse()

    repeated = request.GET.get('repeated', 0)
    action = u'{}?step={}&repeated={}'.format(reverse('phone_automation_call_flow_menu_options'), current_step.step, repeated)
    gather = Gather(num_digits=1, action=action)

    if config.get('mp3'):
        gather.play(config.get('mp3'))
    elif config.get('say'):
        gather.say(config.get('say'), voice=config.get('voice'))
    response.append(gather)
    response.redirect(action)

    return HttpResponse(str(response), content_type='application/xml')


def call_flow_menu_options(request):
    phone = TwilioPhoneNumber.objects.get(incoming_number=request.POST.get('To'))
    current_step = phone.automation.steps.get(step=request.GET.get('step'))
    config = current_step.get_config()

    response = VoiceResponse()
    choice = safeInt(request.POST.get('Digits'))
    for children_step in current_step.children.all():
        children_config = children_step.get_config()
        if children_config.get('number') == choice:
            response.redirect(children_step.redirect)
            break
    else:
        repeat = config.get('repeat', False)
        repeated = safeInt(request.GET.get('repeated', 0))
        if repeat and repeated < 1:
            repeated += 1
            response.redirect(u'{}&repeated={}'.format(current_step.url, repeated))
        else:
            response.redirect(current_step.redirect)

    return HttpResponse(str(response), content_type='application/xml')


def call_flow_record(request):
    phone = TwilioPhoneNumber.objects.get(incoming_number=request.POST.get('To'))
    current_step = phone.automation.steps.get(step=request.GET.get('step'))
    config = current_step.get_config()

    response = VoiceResponse()
    if config.get('mp3'):
        response.play(config.get('mp3'))
    elif config.get('say'):
        response.say(config.get('say'), voice=config.get('voice'))

    response.record(timeout=5, playBeep=config.get('play_beep', True), action=current_step.redirect)
    return HttpResponse(str(response), content_type='application/xml')


def call_flow_dial(request):
    phone = TwilioPhoneNumber.objects.get(incoming_number=request.POST.get('To'))
    current_step = phone.automation.steps.get(step=request.GET.get('step'))
    config = current_step.get_config()

    response = VoiceResponse()
    if config.get('mp3'):
        response.play(config.get('mp3'))
    elif config.get('say'):
        response.say(config.get('say'), voice=config.get('voice'))

    response.dial(config.get('phone'), action=current_step.redirect)
    return HttpResponse(str(response), content_type='application/xml')


def call_flow_hangup(request):
    response = VoiceResponse()
    response.hangup()

    return HttpResponse(str(response), content_type='application/xml')


def call_flow_empty(request):
    phone = TwilioPhoneNumber.objects.get(incoming_number=request.POST.get('To'))
    current_step = phone.automation.steps.get(step=request.GET.get('step'))

    response = VoiceResponse()
    response.redirect(current_step.redirect)

    return HttpResponse(str(response), content_type='application/xml')


def status_callback(request):
    # searching related phone number
    twilio_phone_number = TwilioPhoneNumber.objects.get(incoming_number=request.POST.get('To'))

    if twilio_phone_number and request.POST.get('CallStatus') == 'completed':
        twilio_log = TwilioLog()
        twilio_log.user = twilio_phone_number.user
        twilio_log.from_number = request.POST.get('From')
        twilio_log.direction = request.POST.get('Direction')
        twilio_log.call_duration = request.POST.get('CallDuration')
        twilio_log.call_sid = request.POST.get('CallSid')
        twilio_log.call_status = request.POST.get('CallStatus')
        twilio_log.log_type = 'status-callback'
        twilio_metadata = json.dumps(request.POST, default=JsonDatetimeConverter)
        twilio_log.twilio_metadata = twilio_metadata
        twilio_log.save()

        # fetch recordings
        try:
            client = get_twilio_client()
            recordings = client.recordings.list(call_sid=twilio_log.call_sid)
            for recording in recordings:
                twilio_recording = TwilioRecording()
                twilio_recording.twilio_log = twilio_log
                twilio_recording.recording_sid = recording.sid
                twilio_recording.recording_url = u"https://api.twilio.com/{}.mp3".format(recording.uri.rsplit('.json', 1)[0])
                twilio_metadata = json.dumps(recording._properties, default=JsonDatetimeConverter)
                twilio_recording.twilio_metadata = twilio_metadata
                twilio_recording.save()

        except:
            raven_client.captureException()

    return HttpResponse(status=200)
