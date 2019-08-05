import json
import mimetypes
from datetime import timedelta, datetime
import re
import arrow
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.db.models import Sum
from django.utils import timezone
from django.utils.crypto import get_random_string
from raven.contrib.django.raven_compat.models import client as raven_client

from twilio.base.exceptions import TwilioRestException
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.twiml.messaging_response import MessagingResponse

from leadgalaxy.utils import aws_s3_upload
from shopified_core.utils import safe_int, app_link, safe_float
from shopified_core.decorators import no_subusers
from .forms import TwilioAlertForm, TwilioProvisionForm, TwilioPhoneNumberForm, TwilioAutomationForm, \
    TwilioCompanyForm, TwilioSummaryForm
from .models import (
    TwilioPhoneNumber,
    TwilioUpload,
    TwilioLog,
    TwilioRecording,
    TwilioAutomation,
    TwilioCompany,
    TwilioAlert,
    TwilioSummary
)
from .utils import (
    get_month_totals,
    get_month_limit,
    get_twilio_client,
    get_orders_by_phone,
    get_sms_text,
    get_orders_by_id,
    check_sms_abilities,
    check_callflex_warnings,
    check_provision_access,
    get_unused_subscription,
    get_phonenumber_usage
)
from . import notifications_utils as notifications
from . import billing_utils as billing


def JsonDatetimeConverter(o):
    if isinstance(o, datetime):
        return o.__str__()


@login_required
def index(request):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    user = request.user.models_user
    twilio_phone_numbers = user.twilio_phone_numbers
    twilio_automations = user.twilio_automations

    try:
        twilio_stats = {}
        twilio_logs = user.twilio_logs.filter(log_type='status-callback')
        latest_twilio_logs = twilio_logs[:5]
        twilio_stats['twilio_logs_total_count'] = twilio_logs.count()
        day_start = timezone.now().replace(hour=12, minute=0, second=0)
        today_twilio_logs = twilio_logs.filter(created_at__gte=day_start)
        twilio_stats['twilio_logs_today_count'] = today_twilio_logs.count()
        twilio_stats['today_total_duration'] = safe_int(today_twilio_logs.aggregate(Sum('call_duration')))
        twilio_stats['total_duration'] = get_month_totals(user)
        twilio_stats['total_duration_month_limit'] = get_month_limit(user)
        twilio_stats['today_uniq_callers_count'] = today_twilio_logs.values('from_number').distinct().count()
    except:
        raven_client.captureException()
        latest_twilio_logs = []
        twilio_stats = False

    if (twilio_phone_numbers.count() <= 0) and latest_twilio_logs == []:
        return HttpResponseRedirect(reverse('phone_automation_provision'))

    for twilio_phone_number in twilio_phone_numbers.all():
        # checking SMS abilities
        sms_allowed = check_sms_abilities(twilio_phone_number)

        if request.user.can('phone_automation_sms.use') and sms_allowed:
            twilio_phone_number.sms_allowed = True
        else:
            twilio_phone_number.sms_allowed = False

    return render(request, 'phone_automation/index.html', {
        'selected_menu': 'tools:phone_automation',
        'page': ('phone_automation', 'phone_automation_index'),
        'twilio_phone_numbers': twilio_phone_numbers.all(),
        'twilio_automations': twilio_automations.all(),
        'twilio_logs': latest_twilio_logs,
        'twilio_stats': twilio_stats,
        'companies': user.twilio_companies.all(),
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'My Numbers'],
    })


@login_required
def callflows_index(request):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    user = request.user.models_user
    twilio_automations = user.twilio_automations

    return render(request, 'phone_automation/automations_index.html', {
        'selected_menu': 'tools:phone_automation',
        'page': ('phone_automation', 'phone_automations_index'),
        'twilio_automations': twilio_automations.all(),
        'companies': user.twilio_companies.all(),
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'My CallFlows'],
    })


@login_required
def call_logs(request):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    user = request.user.models_user

    # filters
    date_now = arrow.get(timezone.now())
    created_at_daterange = request.GET.get('created_at_daterange',
                                           '{}-'.format(date_now.replace(days=-30).format('MM/DD/YYYY')))
    created_at_end = None
    created_at_start = None
    if created_at_daterange:
        try:
            daterange_list = created_at_daterange.split('-')
            tz = timezone.localtime(timezone.now()).strftime(' %z')
            created_at_start = arrow.get(daterange_list[0] + tz, r'MM/DD/YYYY Z').datetime

            if len(daterange_list) > 1 and daterange_list[1]:
                created_at_end = arrow.get(daterange_list[1] + tz, r'MM/DD/YYYY Z')
                created_at_end = created_at_end.span('day')[1].datetime
        except:
            pass

    call_status = request.GET.get('call_status', None)
    company_id = request.GET.get('company_id', None)

    try:
        twilio_stats = {}
        twilio_logs = user.twilio_logs.filter(log_type='status-callback')

        if created_at_start:
            twilio_logs = twilio_logs.filter(created_at__gte=created_at_start)

        if created_at_end:
            twilio_logs = twilio_logs.filter(created_at__lte=created_at_end)

        if call_status and call_status != '':
            twilio_logs = twilio_logs.filter(call_status=call_status)

        if company_id and company_id != '':
            twilio_logs = twilio_logs.filter(twilio_phone_number__company_id=company_id)

        twilio_logs = twilio_logs.order_by('-created_at')

    except:
        raven_client.captureException()
        twilio_logs = []
        twilio_stats = False

    # getting data for chart
    twilio_logs_chart = user.twilio_logs.filter(log_type='status-callback')

    today = timezone.now()
    last_7_days = []

    for f in range(-7, 0):
        day = today + timedelta(f)
        day_str = day

        twilio_logs_chart = user.twilio_logs.filter(log_type='status-callback')
        twilio_logs_chart = twilio_logs_chart.filter(created_at__gte=day)
        twilio_logs_chart = twilio_logs_chart.filter(created_at__lte=(day + timedelta(1)))
        count = twilio_logs_chart.all().count()

        last_7_days.append({"x": day_str, "y": count})

    charts_data = {"last_7_days": last_7_days}

    return render(request, 'phone_automation/call_logs.html', {
        'selected_menu': 'tools:phone_automation',
        'page': ('phone_automation', 'phone_automation_call_logs'),
        'twilio_logs': twilio_logs,
        'twilio_stats': twilio_stats,
        'companies': user.twilio_companies.all(),
        'charts_data': charts_data,
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'Call Logs'],
    })


@login_required
@no_subusers
@transaction.atomic
def call_log_save(request, twilio_log_id):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    user = request.user.models_user
    twilio_log = user.twilio_logs.filter(pk=twilio_log_id).first()
    twilio_log.notes = request.POST.get("note")
    twilio_log.save()

    return JsonResponse({'status': 'ok'})


@login_required
@no_subusers
@transaction.atomic
def provision(request):
    user = request.user.models_user
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    overages_warning = False
    overages_warning_phone_price = False

    phonenumber_usage = get_phonenumber_usage(user)
    if phonenumber_usage['total'] and phonenumber_usage['used'] >= \
            phonenumber_usage['total'] + settings.CALLFLEX_OVERAGES_MAX_NUMBERS:
        return render(request, 'phone_automation/callflex_upgrade.html')

    client = get_twilio_client()
    if request.method == 'POST':
        phone_number = request.POST.get("phone_number")
        title = request.POST.get("title")
        automation_id = request.POST.get("automation")
        sms_enabled = request.POST.get("sms_enabled")
        forwarding_number = request.POST.get("forwarding_number")
        company = request.POST.get("company")
        phone_number_type = request.POST.get("phone_number_type")
        try:
            if not check_provision_access(request.user, phone_number_type):

                if user.profile.from_shopify_app_store():
                    try:
                        # getting last created active shopify subscriptioon
                        shopify_subscription = billing.get_shopify_recurring(request.user)
                        if shopify_subscription:
                            # subscription exists
                            pass
                        else:
                            profile_link = app_link(reverse('user_profile'))
                            messages.error(request,
                                           'Error while provisioning this phone number. There is no shopify active subscription. '
                                           f'Please check your <a href="{profile_link}?callflex_anchor#plan">Profile</a> page for details')
                            return HttpResponseRedirect(reverse('phone_automation_provision'))
                    except:
                        messages.error(request, 'Error while provisioning this phone number. There is no active shopify subscription')
                        return HttpResponseRedirect(reverse('phone_automation_provision'))
                else:
                    overages = billing.CallflexOveragesBilling(user)
                    try:
                        if phone_number_type == "tollfree":
                            overages_warning_phone_price = settings.EXTRA_TOLLFREE_NUMBER_PRICE
                            overages.add_invoice('extra_number', overages_warning_phone_price, False)
                        if phone_number_type == "local":
                            overages_warning_phone_price = settings.EXTRA_LOCAL_NUMBER_PRICE
                            overages.add_invoice('extra_number', overages_warning_phone_price, False)
                    except Exception:
                        raven_client.captureException()
                        messages.error(request,
                                       'Error while provisioning phone number. Please subscribe to a CallFlex plan')
                        return HttpResponseRedirect(reverse('phone_automation_provision'))
            incoming_phone_number = client.incoming_phone_numbers \
                .create(
                    phone_number=phone_number,
                    voice_url=app_link(reverse('phone_automation_call_flow')),
                    sms_url=app_link(reverse('phone_automation_sms_flow')),
                    status_callback=app_link(reverse('phone_automation_status_callback'))
                )
            twilio_metadata = incoming_phone_number._properties
            twilio_metadata = json.dumps(twilio_metadata, default=JsonDatetimeConverter)
            twilio_metadata = json.loads(twilio_metadata)

            twilio_phone_number = TwilioPhoneNumber()
            twilio_phone_number.incoming_number = phone_number
            twilio_phone_number.user_id = user.id
            twilio_phone_number.type = phone_number_type
            twilio_phone_number.twilio_metadata = twilio_metadata
            twilio_phone_number.twilio_sid = incoming_phone_number.sid
            twilio_phone_number.forwarding_number = forwarding_number
            twilio_phone_number.company_id = company

            # getting unused custom subscription to assign
            unused_subscription = get_unused_subscription(request.user)
            twilio_phone_number.custom_subscription = unused_subscription

            if automation_id != '' and safe_int(automation_id):
                automation = user.twilio_automations.filter(id=automation_id).first() or None
                twilio_phone_number.automation = automation
            twilio_phone_number.title = title

            if sms_enabled == "on":
                twilio_phone_number.sms_enabled = True

            twilio_phone_number.save()

            messages.success(request, 'Phone Number has been successfully set')
            return HttpResponseRedirect(reverse('phone_automation_index'))

        except TwilioRestException:
            raven_client.captureException()
            messages.error(request, 'Error while provisioning this phone number. Please try another one.')
            return HttpResponseRedirect(reverse('phone_automation_provision'))
        except Exception:
            raven_client.captureException()

            messages.error(request, 'Error while provisioning this phone number, please try another one. ')
            return HttpResponseRedirect(reverse('phone_automation_provision'))
    else:
        areacode = request.GET.get("areacode")
        mask = request.GET.get("mask")
        country_code = request.GET.get("country_code")
        allowed_country_codes = ["US", "CA"]
        if country_code not in allowed_country_codes:
            country_code = "US"
        phone_type = request.GET.get("phone_type", "tollfree")

        if not check_provision_access(request.user, phone_type):
            overages_warning = True
            if phone_type == "tollfree":
                overages_warning_phone_price = settings.EXTRA_TOLLFREE_NUMBER_PRICE
            if phone_type == "local":
                overages_warning_phone_price = settings.EXTRA_LOCAL_NUMBER_PRICE
        else:
            overages_warning = False

        if areacode or mask:
            show_filter = True
        else:
            show_filter = False

        form = TwilioProvisionForm(request.GET, user=user)
        numbers = []
        try:
            if phone_type == "local":
                numbers = client.available_phone_numbers(country_code) \
                    .local \
                    .list(voice_enabled=True, sms_enabled=True, area_code=areacode, contains=mask, page_size=12)
            else:
                phone_type == "tollfree"
                numbers = client.available_phone_numbers(country_code) \
                    .toll_free \
                    .list(voice_enabled=True, sms_enabled=True, area_code=areacode, contains=mask, page_size=12)
        except Exception:
            numbers = []
            messages.error(request, 'Error while searching phone number. Try another search patterns.')

        twilio_phone_numbers_pool = numbers

    return render(request, 'phone_automation/provision.html', {
        'page': 'phone_automation',
        'selected_menu': 'tools:phone_automation',
        'show_filter': show_filter,
        'form': form,
        'twilio_phone_numbers_pool': twilio_phone_numbers_pool,
        'phone_number_type': phone_type,
        'overages_warning': overages_warning,
        'overages_extra_number_price': overages_warning_phone_price,
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'Setup Incoming Phone #'],
    })


@login_required
@transaction.atomic
def provision_edit(request, twilio_phone_number_id):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    user = request.user.models_user
    twilio_phone_number = get_object_or_404(TwilioPhoneNumber, pk=twilio_phone_number_id, user=user)

    if request.method == 'POST':
        form = TwilioPhoneNumberForm(request.POST, instance=twilio_phone_number, user=user)
        if form.is_valid():
            twilio_phone_number = form.save()
            messages.success(request, 'Phone Number  has been successfully updated')
            return HttpResponseRedirect(reverse('phone_automation_index'))
    else:
        form = TwilioPhoneNumberForm(instance=twilio_phone_number, user=user)

    return render(request, 'phone_automation/provision_edit.html', {
        'selected_menu': 'tools:phone_automation',
        'page': 'phone_automation',
        'form': form,
        'twilio_phone_number': twilio_phone_number,
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'Edit Incoming Phone #'],
    })


@login_required
@no_subusers
@transaction.atomic
def provision_release(request, twilio_phone_number_id):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    user = request.user.models_user
    twilio_phone_number = get_object_or_404(TwilioPhoneNumber, pk=twilio_phone_number_id, user=user)

    removal_avail_date = twilio_phone_number.created_at + timedelta(days=30)

    if not request.user.can('phone_automation_unlimited_phone_numbers.use') and timezone.now() < removal_avail_date:
        messages.error(request, 'You can not remove this phone number until {}'.format(removal_avail_date.strftime("%b %d, %Y")))
        return HttpResponseRedirect(reverse('phone_automation_index'))

    try:
        twilio_phone_number.delete()
        messages.success(request, 'Phone number has been successfully removed')
        return HttpResponseRedirect(reverse('phone_automation_index'))

    except:
        raven_client.captureException()
        messages.error(request, 'Error while removing phone number. ')
        return HttpResponseRedirect(reverse('phone_automation_index'))


def status_callback(request):
    # searching related phone number
    twilio_phone_number = get_object_or_404(TwilioPhoneNumber, incoming_number=request.POST.get('To'))

    if twilio_phone_number and request.POST.get('CallStatus') in ('completed', 'busy', 'failed', 'no-answer'):
        # --- check for reaching limit warning
        check_callflex_warnings(twilio_phone_number.user, request.POST.get('CallDuration'))

        twilio_log = TwilioLog()
        twilio_log.twilio_phone_number = twilio_phone_number
        twilio_log.user = twilio_phone_number.user
        twilio_log.from_number = request.POST.get('From')
        twilio_log.direction = request.POST.get('Direction')
        twilio_log.call_duration = request.POST.get('CallDuration')
        twilio_log.call_sid = request.POST.get('CallSid')
        twilio_log.call_status = request.POST.get('CallStatus')
        twilio_log.log_type = 'status-callback'
        twilio_metadata = json.dumps(request.POST, default=JsonDatetimeConverter)
        twilio_log.twilio_metadata = json.loads(twilio_metadata)
        twilio_log.phone_type = twilio_phone_number.type
        twilio_log.save()

        # process overages

        total_duration = get_month_totals(twilio_phone_number.user, twilio_log.phone_type)
        total_duration_month_limit = get_month_limit(twilio_phone_number.user, twilio_log.phone_type)

        # if monthly limit reached, add averages into invoice
        if total_duration_month_limit is not False and total_duration \
                and total_duration > total_duration_month_limit:
            overages = billing.CallflexOveragesBilling(twilio_phone_number.user)
            if twilio_log.phone_type == "tollfree":
                extra_minute_price = settings.EXTRA_TOLLFREE_MINUTE_PRICE
            if twilio_log.phone_type == "local":
                extra_minute_price = settings.EXTRA_LOCAL_MINUTE_PRICE

            try:
                if twilio_phone_number.user.profile.from_shopify_app_store():
                    overages.add_shopify_usage_invoice('extra_minutes', extra_minute_price * safe_float(
                        request.POST.get('CallDuration')) / 60, False)
                else:
                    overages.add_invoice('extra_minutes', extra_minute_price * safe_float(
                        request.POST.get('CallDuration')) / 60, False)
            except:
                raven_client.captureException()
        # fetch recordings
        try:
            client = get_twilio_client()
            recordings = client.recordings.list(call_sid=twilio_log.call_sid)
            for recording in recordings:
                twilio_recording = TwilioRecording()
                twilio_recording.twilio_log = twilio_log
                twilio_recording.recording_sid = recording.sid
                twilio_recording.recording_url = "https://api.twilio.com/{}.mp3".format(recording.uri.rsplit('.json', 1)[0])
                twilio_metadata = json.dumps(recording._properties, default=JsonDatetimeConverter)
                twilio_recording.twilio_metadata = twilio_metadata
                twilio_recording.save()

                # TODO: billing recordings can be added here later

        except:
            raven_client.captureException()

        # Process alerts
        try:
            alert_notification = notifications.AlertNotification(twilio_phone_number, twilio_log)
            alert_notification.process_alerts()
        except:
            raven_client.captureException()

    return HttpResponse(status=200)


# Call Flow
@login_required
def save_automation(request, twilio_automation_id=None):
    user = request.user.models_user

    if twilio_automation_id:
        twilio_automation = TwilioAutomation.objects.get(pk=twilio_automation_id)
    else:
        twilio_automation = None   # Create form

    # Form will save nodes in correct order after saving the automation object
    form = TwilioAutomationForm(request.POST, instance=twilio_automation)
    if form.is_valid():
        # First save must occur so steps are properly saved
        twilio_automation = form.save()
        twilio_automation.user = user
        twilio_automation.save()

        return JsonResponse({'status': 'ok'})
    else:
        return JsonResponse({'status': 'error', 'errors': form.errors}, status=500)


@login_required
def delete_automation(request, twilio_automation_id=None):
    user = request.user.models_user
    twilio_automation = get_object_or_404(TwilioAutomation, pk=twilio_automation_id, user=user)
    twilio_automation.delete()
    messages.error(request, 'CallFlow has been successfully deleted')
    return HttpResponseRedirect(reverse('phone_automations_index'))


@login_required
def automate(request, twilio_automation_id=None):

    if twilio_automation_id:
        twilio_automation = get_object_or_404(TwilioAutomation, pk=twilio_automation_id, user=request.user.models_user)
    else:
        twilio_automation = None   # Create form

    return render(request, 'phone_automation/automate.html', {
        'automation': twilio_automation,
        'page': 'phone_automation',
        'selected_menu': 'tools:phone_automation',
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automations_index')}, 'Automate'],
    })


@login_required
def upload(request, twilio_automation_id):
    user = request.user.models_user
    if twilio_automation_id:
        twilio_automation = request.user.twilio_automations.filter(pk=twilio_automation_id).first()
    else:
        twilio_automation = None

    audio = request.FILES.get('mp3')
    step = request.POST.get('step')

    # Randomize filename in order to not overwrite an existing file
    ext = audio.name.split('.')[1:]
    random_name = get_random_string(length=10)
    audio_name = 'uploads/u{}/phone/{}/s-{}/{}'.format(user.id, random_name, step, '.'.join(ext))
    mimetype = mimetypes.guess_type(audio.name)[0]

    upload_url = aws_s3_upload(
        filename=audio_name,
        fp=audio,
        mimetype=mimetype,
        bucket_name=settings.S3_UPLOADS_BUCKET
    )

    twilio_upload = TwilioUpload.objects.create(
        user=user,
        automation=twilio_automation,
        url=upload_url[:510]
    )

    return JsonResponse({
        'status': 'ok',
        'url': upload_url,
        'id': twilio_upload.id
    })


def call_flow(request):
    phone = get_object_or_404(TwilioPhoneNumber, incoming_number=request.POST.get('To'))
    response = VoiceResponse()

    total_duration = get_month_totals(phone.user)
    total_duration_month_limit = get_month_limit(phone.user)

    # if CALLFLEX_OVERAGES_MAX_MINUTES limit reached, reject the call
    if total_duration_month_limit and total_duration \
            and total_duration > total_duration_month_limit + settings.CALLFLEX_OVERAGES_MAX_MINUTES:
        response.reject()
    elif phone.automation is None:
        if phone.forwarding_number != '':

            response.dial(phone.forwarding_number)
        else:
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
        response.play('{}.converted.mp3'.format(config.get('mp3')))
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
    action = '{}?step={}&repeated={}'.format(reverse('phone_automation_call_flow_menu_options'), current_step.step, repeated)
    gather = Gather(num_digits=1, action=action)

    if config.get('mp3'):
        gather.play('{}.converted.mp3'.format(config.get('mp3')))
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
    choice = safe_int(request.POST.get('Digits'))
    for children_step in current_step.children.all():
        children_config = children_step.get_config()
        if children_config.get('number') == choice:
            next_step_children = children_step.children.first()
            response.redirect(next_step_children.url)
            break
    else:
        repeat = config.get('repeat', False)
        repeated = safe_int(request.GET.get('repeated', 0))
        if repeat and repeated < 1:
            repeated += 1
            response.redirect('{}&repeated={}'.format(current_step.url, repeated))
        else:
            response.redirect(current_step.redirect)

    return HttpResponse(str(response), content_type='application/xml')


def call_flow_record(request):
    phone = TwilioPhoneNumber.objects.get(incoming_number=request.POST.get('To'))
    current_step = phone.automation.steps.get(step=request.GET.get('step'))
    config = current_step.get_config()

    response = VoiceResponse()
    if config.get('mp3'):
        response.play('{}.converted.mp3'.format(config.get('mp3')))
    elif config.get('say'):
        response.say(config.get('say'), voice=config.get('voice'))

    response.record(timeout=5, playBeep=config.get('play_beep', True), action=reverse('phone_automation_call_flow_hangup'))
    return HttpResponse(str(response), content_type='application/xml')


def call_flow_dial(request):
    phone = TwilioPhoneNumber.objects.get(incoming_number=request.POST.get('To'))
    current_step = phone.automation.steps.get(step=request.GET.get('step'))
    config = current_step.get_config()

    response = VoiceResponse()
    if config.get('mp3'):
        response.play('{}.converted.mp3'.format(config.get('mp3')))
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


def sms_flow(request):
    phone = TwilioPhoneNumber.objects.get(incoming_number=request.POST.get('To'))
    user = phone.user
    phone_from = request.POST.get('From')
    sms_message = request.POST.get('Body')

    response = MessagingResponse()

    command_order_phone = re.search(r'(orders-phone) (.*)', sms_message)
    command_orders = re.search(r'(orders)(.*)', sms_message)
    command_order_id = re.search(r'(order-id) (.*)', sms_message)

    message = ""

    if command_order_phone:
        # getting order by phone number
        command_parameter = command_order_phone.group(2).strip()
        phone_cleaned = re.sub(r"\D", "", command_parameter)
        orders = get_orders_by_phone(user, phone_cleaned, command_parameter)

        if len(orders['shopify']) > 0 or len(orders['woo']) > 0 or len(orders['chq']) > 0 or len(orders['gear']) > 0:
            message += f"We've found the following open orders by your phone number {command_parameter}: \n "
            message += get_sms_text(orders)

        else:
            message += f"We've not found any open orders by your phone number {command_parameter} . \n "
    elif command_orders:
        # getting order by phone number
        phone = re.sub(r"\D", "", phone_from)

        orders = get_orders_by_phone(user, phone, phone_from)

        if len(orders['shopify']) > 0 or len(orders['woo']) > 0 or len(orders['chq']) > 0 or len(orders['gear']) > 0:
            message += f"We've found the following open orders by your phone number {phone_from}: \n "
            message += get_sms_text(orders)

        else:
            message += f"We've not found any open orders by your phone number {phone_from} . \n "

    elif command_order_id:
        command_parameter = command_order_id.group(2).strip()
        command_parameter = re.sub(r"\D", "", command_parameter)

        # getting order by ID
        order_id = command_parameter

        orders = get_orders_by_id(user, order_id)
        if len(orders['shopify']) > 0 or len(orders['woo']) > 0 or len(orders['chq']) > 0 or len(orders['gear']) > 0:
            message += f"We've found the following open orders by ID you provided ({order_id}): \n "
            message += get_sms_text(orders)

        else:
            message += f"We've not found any open orders by ID you sent us ({order_id}). \n "

    else:
        message = "Command not recognized."

    response.message(message)

    return HttpResponse(response, content_type='application/xml')


@login_required
def companies_index(request):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    user = request.user.models_user

    twilio_companies = user.twilio_companies

    return render(request, 'phone_automation/companies_index.html', {
        'selected_menu': 'tools:phone_automation',
        'page': ('phone_automation', 'phone_automation_account', 'phone_automation_companies_index'),
        'twilio_companies': twilio_companies.all(),
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'My Companies'],
    })


@login_required
def companies_edit(request, company_id=False):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    user = request.user.models_user
    if company_id:
        twilio_company = user.twilio_companies.filter(pk=company_id).first()
        users = twilio_company.get_config_users
    else:
        twilio_company = TwilioCompany()
        twilio_company.user = user
        users = twilio_company.get_profile_users

    if request.method == 'POST':
        form = TwilioCompanyForm(request.POST, instance=twilio_company)
        if form.is_valid():
            twilio_company = form.save()

            users_json_str = request.POST.get('users', [])
            twilio_company.config = json.dumps({"users": json.loads(users_json_str)})
            twilio_company.save()

            messages.success(request, 'Company has been successfully updated')
            return HttpResponseRedirect(reverse('phone_automation_companies_index'))
    else:
        form = TwilioCompanyForm(instance=twilio_company)

    return render(request, 'phone_automation/company_form.html', {
        'selected_menu': 'tools:phone_automation',
        'page': ('phone_automation', 'phone_automation_companies_index'),
        'twilio_company': twilio_company,
        'form': form,
        'users': users,
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'My Companies'],
    })


@login_required
def companies_delete(request, company_id=False):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)
    user = request.user.models_user
    twilio_company = get_object_or_404(TwilioCompany, pk=company_id, user=user)
    twilio_company.delete()
    messages.error(request, 'Company has been successfully deleted')
    return HttpResponseRedirect(reverse('phone_automation_companies_index'))


@login_required
def reports_numbers(request):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    user = request.user.models_user

    # filters
    date_now = arrow.get(timezone.now())
    created_at_daterange = request.GET.get('created_at_daterange',
                                           '{}-'.format(date_now.replace(days=-30).format('MM/DD/YYYY')))
    created_at_end = None
    created_at_start = None
    if created_at_daterange:
        try:
            daterange_list = created_at_daterange.split('-')
            tz = timezone.localtime(timezone.now()).strftime(' %z')
            created_at_start = arrow.get(daterange_list[0] + tz, r'MM/DD/YYYY Z').datetime

            if len(daterange_list) > 1 and daterange_list[1]:
                created_at_end = arrow.get(daterange_list[1] + tz, r'MM/DD/YYYY Z')
                created_at_end = created_at_end.span('day')[1].datetime
        except:
            pass

    company_id = request.GET.get('company_id', None)
    companies = user.twilio_companies.all()
    twilio_logs = []
    try:
        twilio_phone_numbers = user.twilio_phone_numbers.all()

        if company_id and company_id != '':
            twilio_phone_numbers = twilio_phone_numbers.filter(company_id=company_id)
        twilio_phone_numbers = twilio_phone_numbers.all()

        for twilio_phone_number in twilio_phone_numbers:
            twilio_logs = twilio_phone_number.twilio_logs.filter(log_type='status-callback')

            if created_at_start:
                twilio_logs = twilio_logs.filter(created_at__gte=created_at_start)

            if created_at_end:
                twilio_logs = twilio_logs.filter(created_at__lte=created_at_end)

            stats = {}
            stats['total_calls'] = twilio_logs.count()
            stats['total_minutes'] = safe_int(twilio_logs.aggregate(Sum('call_duration'))['call_duration__sum'])
            twilio_phone_number.stats = stats
    except:
        raven_client.captureException()

    return render(request, 'phone_automation/reports_numbers.html', {
        'selected_menu': 'tools:phone_automation',
        'page': ('phone_automation', 'phone_automation_reports', 'phone_automation_reports_numbers'),
        'twilio_logs': twilio_phone_numbers,
        'companies': companies,
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'Reports by numbers'],
    })


@login_required
def reports_companies(request):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    user = request.user.models_user

    # filters
    date_now = arrow.get(timezone.now())
    created_at_daterange = request.GET.get('created_at_daterange',
                                           '{}-'.format(date_now.replace(days=-30).format('MM/DD/YYYY')))
    created_at_end = None
    created_at_start = None
    if created_at_daterange:
        try:
            daterange_list = created_at_daterange.split('-')
            tz = timezone.localtime(timezone.now()).strftime(' %z')
            created_at_start = arrow.get(daterange_list[0] + tz, r'MM/DD/YYYY Z').datetime

            if len(daterange_list) > 1 and daterange_list[1]:
                created_at_end = arrow.get(daterange_list[1] + tz, r'MM/DD/YYYY Z')
                created_at_end = created_at_end.span('day')[1].datetime
        except:
            pass
    twilio_logs = []
    try:
        twilio_companies = user.twilio_companies.all()

        for twilio_company in twilio_companies:
            twilio_logs = user.twilio_logs.filter(log_type='status-callback', twilio_phone_number__company_id=twilio_company.id)

            if created_at_start:
                twilio_logs = twilio_logs.filter(created_at__gte=created_at_start)

            if created_at_end:
                twilio_logs = twilio_logs.filter(created_at__lte=created_at_end)

            stats = {}
            stats['total_numbers'] = twilio_company.phones.all().count()
            stats['total_calls'] = twilio_logs.count()
            stats['total_minutes'] = safe_int(twilio_logs.aggregate(Sum('call_duration'))['call_duration__sum'])
            twilio_company.stats = stats
    except:
        raven_client.captureException()

    return render(request, 'phone_automation/reports_companies.html', {
        'selected_menu': 'tools:phone_automation',
        'page': ('phone_automation', 'phone_automation_reports', 'phone_automation_reports_companies'),
        'twilio_logs': twilio_companies,
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'Reports by numbers'],
    })


@login_required
@transaction.atomic
def notifications_alerts(request):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    user = request.user.models_user
    alerts = user.twilio_alerts.all()

    return render(request, 'phone_automation/notifications_alerts.html', {
        'selected_menu': 'tools:phone_automation',
        'page': ('phone_automation', 'phone_automation_notifications', 'phone_automation_notifications_alerts'),
        'alerts': alerts,
        'companies': user.twilio_companies.all(),
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'Alerts'],
    })


@login_required
def notifications_alert_edit(request, company_id=False, alert_id=False):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    if company_id is False and alert_id is False:
        HttpResponse(status=404)

    user = request.user.models_user
    if alert_id:
        twilio_alert = user.twilio_alerts.filter(pk=alert_id).first()
        company_users = twilio_alert.company.get_config_users()
        config_users = twilio_alert.get_config_users()

        for company_user in company_users:
            if company_user in config_users:
                company_user['checked'] = True
        users = company_users
    else:
        twilio_alert = TwilioAlert()
        twilio_alert.user = user
        company = user.twilio_companies.filter(pk=company_id).first()
        twilio_alert.company = company
        users = company.get_config_users()

    if request.method == 'POST':
        form = TwilioAlertForm(request.POST, instance=twilio_alert)
        if form.is_valid():
            twilio_alert = form.save()

            users_json_str = request.POST.get('users', [])
            twilio_alert.config = json.dumps({"users": json.loads(users_json_str)})
            twilio_alert.save()

            messages.success(request, 'Alert has been successfully updated')
            return HttpResponseRedirect(reverse('phone_automation_notifications_alerts'))
    else:

        form = TwilioAlertForm(instance=twilio_alert)

    return render(request, 'phone_automation/alert_form.html', {
        'selected_menu': 'tools:phone_automation',
        'page': ('phone_automation', 'phone_automation_notifications', 'phone_automation_notifications_alerts'),
        'twilio_alert': twilio_alert,
        'form': form,
        'users': users,

        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'My Alerts'],
    })


@login_required
def notifications_alert_delete(request, alert_id):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)
    user = request.user.models_user
    twilio_alert = get_object_or_404(TwilioAlert, pk=alert_id, user=user)
    twilio_alert.delete()
    messages.error(request, 'Alert has been successfully deleted')
    return HttpResponseRedirect(reverse('phone_automation_notifications_alerts'))


@login_required
@transaction.atomic
def notifications_summaries(request):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    user = request.user.models_user
    summaries = user.twilio_summaries.all()

    return render(request, 'phone_automation/notifications_summaries.html', {
        'selected_menu': 'tools:phone_automation',
        'page': ('phone_automation', 'phone_automation_notifications', 'phone_automation_notifications_summaries'),
        'summaries': summaries,
        'companies': user.twilio_companies.all(),
        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'Summaries'],
    })


@login_required
def notifications_summary_edit(request, company_id=False, summary_id=False):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)

    if company_id is False and summary_id is False:
        HttpResponse(status=404)

    user = request.user.models_user
    if summary_id:
        twilio_summary = user.twilio_summaries.filter(pk=summary_id).first()
        company_users = twilio_summary.company.get_config_users()
        config_users = twilio_summary.get_config_users()

        for company_user in company_users:
            if company_user in config_users:
                company_user['checked'] = True
        users = company_users

    else:
        twilio_summary = TwilioSummary()
        twilio_summary.user = user
        company = user.twilio_companies.filter(pk=company_id).first()
        twilio_summary.company = company
        users = company.get_config_users()

    if request.method == 'POST':
        form = TwilioSummaryForm(request.POST, instance=twilio_summary)
        if form.is_valid():
            twilio_summary = form.save()

            users_json_str = request.POST.get('users', [])
            twilio_summary.config = json.dumps({"users": json.loads(users_json_str)})
            twilio_summary.save()

            messages.success(request, 'Summary has been successfully updated')
            return HttpResponseRedirect(reverse('phone_automation_notifications_summaries'))
    else:

        form = TwilioSummaryForm(instance=twilio_summary)

    return render(request, 'phone_automation/summary_form.html', {
        'selected_menu': 'tools:phone_automation',
        'page': ('phone_automation', 'phone_automation_notifications', 'phone_automation_notifications_summaries'),
        'twilio_summary': twilio_summary,
        'form': form,
        'users': users,

        'breadcrumbs': [{'title': 'CallFlex', 'url': reverse('phone_automation_index')}, 'My Summaries'],
    })


@login_required
def notifications_summary_delete(request, summary_id):
    if not request.user.can('phone_automation.use') or not request.user.can('use_callflex.sub'):
        return render(request, 'upgrade.html', status=403)
    user = request.user.models_user
    twilio_summary = get_object_or_404(TwilioSummary, pk=summary_id, user=user)
    twilio_summary.delete()
    messages.error(request, 'Summary has been successfully deleted')
    return HttpResponseRedirect(reverse('phone_automation_notifications_summaries'))
