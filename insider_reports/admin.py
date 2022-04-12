from django.contrib import admin
from django.shortcuts import reverse
from django.utils.html import format_html

from addons_core.admin import FormWithRequestMixin
from insider_reports.forms import InsiderReportForm
from insider_reports.models import InsiderReport
from shopified_core.utils import app_link


@admin.register(InsiderReport)
class ReportAdmin(FormWithRequestMixin, admin.ModelAdmin):
    form = InsiderReportForm

    list_display = ('report_name', 'link_actions')

    def link_actions(self, obj):
        download_url = app_link(reverse("download_report", kwargs={"report_id": obj.id}))
        html_link = f"""
            <a href="#" onclick="this.children[0].style.display='';
                                 this.children[0].select();
                                 document.execCommand('copy');
                                 this.children[0].style.display='none'">
                Copy Download Link
                <input type="text" style="display: none;"
                       value="{download_url}">
            </a>
        """
        return format_html(html_link)
    link_actions.allow_tags = True
    link_actions.short_description = 'Actions'
