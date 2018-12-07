from django.conf.urls import url

import phone_automation.views

urlpatterns = [
    url(r'^$', phone_automation.views.index, name='phone_automation_index'),
    url(r'^provision$', phone_automation.views.provision, name='phone_automation_provision'),
    url(r'^provision-relese$', phone_automation.views.provision_release, name='phone_automation_provision_release'),
    url(r'^call-logs$', phone_automation.views.call_logs, name='phone_automation_call_logs'),
    url(r'^automate/(?P<twilio_phone_number_id>[\d]+)/save/?$', phone_automation.views.save_automation, name='phone_automation_save_automation'),
    url(r'^automate/(?P<twilio_phone_number_id>[\d]+)/mp3/?$', phone_automation.views.upload, name='phone_automation_upload'),
    url(r'^automate/(?P<twilio_phone_number_id>[\d]+)/?$', phone_automation.views.automate, name='phone_automation_automate'),

    # status callback (for logging and tracking)
    url(r'^status-callback$', phone_automation.views.status_callback, name='phone_automation_status_callback'),

    url(r'^call-flow/?$', phone_automation.views.call_flow, name='phone_automation_call_flow'),
    url(r'^call-flow/speak/?$', phone_automation.views.call_flow_speak, name='phone_automation_call_flow_speak'),
    url(r'^call-flow/menu/?$', phone_automation.views.call_flow_menu, name='phone_automation_call_flow_menu'),
    url(r'^call-flow/menu/options/?$', phone_automation.views.call_flow_menu_options, name='phone_automation_call_flow_menu_options'),
    url(r'^call-flow/record/?$', phone_automation.views.call_flow_record, name='phone_automation_call_flow_record'),
    url(r'^call-flow/dial/?$', phone_automation.views.call_flow_dial, name='phone_automation_call_flow_dial'),
    url(r'^call-flow/empty/?$', phone_automation.views.call_flow_empty, name='phone_automation_call_flow_empty'),

    url(r'^call-flow/hangup/?$', phone_automation.views.call_flow_hangup, name='phone_automation_call_flow_hangup'),
]
