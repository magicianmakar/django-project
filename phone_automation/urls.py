from django.conf.urls import url

import phone_automation.views

urlpatterns = [
    url(r'^$', phone_automation.views.index, name='phone_automation_index'),
    url(r'^provision$', phone_automation.views.provision, name='phone_automation_provision'),
    url(r'^provision/(?P<twilio_phone_number_id>[\d]+)$', phone_automation.views.provision_edit,
        name='phone_automation_provision_edit'),
    url(r'^provision-relese/(?P<twilio_phone_number_id>[\d]+)/?$', phone_automation.views.provision_release,
        name='phone_automation_provision_release'),
    url(r'^call-logs$', phone_automation.views.call_logs, name='phone_automation_call_logs'),
    url(r'^call-log/(?P<twilio_log_id>[\d]+)/save/?$', phone_automation.views.call_log_save, name='phone_automation_call_log_save'),
    url(r'^call-log/delete$', phone_automation.views.call_log_delete, name='phone_automation_call_log_delete'),

    url(r'^reports-numbers$', phone_automation.views.reports_numbers, name='phone_automation_reports_numbers'),
    url(r'^reports-companies$', phone_automation.views.reports_companies, name='phone_automation_reports_companies'),

    url(r'^automations/?$', phone_automation.views.callflows_index, name='phone_automations_index'),
    url(r'^automate/?$', phone_automation.views.automate, name='phone_automation_automate_create'),
    url(r'^automate/(?P<twilio_automation_id>[\d]+)/save/?$', phone_automation.views.save_automation,
        name='phone_automation_save_automation'),
    url(r'^automate/(?P<twilio_automation_id>[\d]+)/delete/?$', phone_automation.views.delete_automation,
        name='phone_automation_delete_automation'),

    url(r'^automate/save/?$', phone_automation.views.save_automation, name='phone_automation_create_automation'),
    url(r'^automate/(?P<twilio_automation_id>[\d]+)?/mp3/?$', phone_automation.views.upload, name='phone_automation_upload'),
    url(r'^automate/(?P<twilio_automation_id>[\d]+)/?$', phone_automation.views.automate, name='phone_automation_automate'),

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


    url(r'^sms-flow/?$', phone_automation.views.sms_flow, name='phone_automation_sms_flow'),

    url(r'^companies/?$', phone_automation.views.companies_index, name='phone_automation_companies_index'),
    url(r'^company/?$', phone_automation.views.companies_edit, name='phone_automation_companies_create'),
    url(r'^company/(?P<company_id>[\d]+)/?$', phone_automation.views.companies_edit,
        name='phone_automation_companies_edit'),
    url(r'^company/(?P<company_id>[\d]+)/delete/?$', phone_automation.views.companies_delete,
        name='phone_automation_companies_delete'),


    url(r'^notifications-alerts$', phone_automation.views.notifications_alerts,
        name='phone_automation_notifications_alerts'),
    url(r'^notifications-alert/(?P<company_id>[\d]+)?/?$', phone_automation.views.notifications_alert_edit,
        name='phone_automation_notifications_alert_create'),
    url(r'^notifications-alert/edit/(?P<alert_id>[\d]+)/?$', phone_automation.views.notifications_alert_edit,
        name='phone_automation_notifications_alert_edit'),
    url(r'^notifications-alert/delete/(?P<alert_id>[\d]+)/?$', phone_automation.views.notifications_alert_delete,
        name='phone_automation_notifications_alert_delete'),

    url(r'^notifications-summaries$', phone_automation.views.notifications_summaries,
        name='phone_automation_notifications_summaries'),
    url(r'^notifications-summary/(?P<company_id>[\d]+)?/?$', phone_automation.views.notifications_summary_edit,
        name='phone_automation_notifications_summary_create'),
    url(r'^notifications-summary/edit/(?P<summary_id>[\d]+)/?$', phone_automation.views.notifications_summary_edit,
        name='phone_automation_notifications_summary_edit'),
    url(r'^notifications-summary/delete/(?P<summary_id>[\d]+)/?$', phone_automation.views.notifications_summary_delete,
        name='phone_automation_notifications_summary_delete'),



]
