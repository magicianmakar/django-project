from django.db import models


class InsiderReport(models.Model):
    report_of = models.DateField(verbose_name="Report Date")
    report_url = models.URLField(default='', blank=True)

    def __str__(self):
        return f'Report for: {self.report_name}'

    @property
    def report_name(self):
        return f'{self.report_of.strftime("%Y-%m-%d")}'
