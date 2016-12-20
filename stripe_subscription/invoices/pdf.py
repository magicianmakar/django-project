import os

from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Table, SimpleDocTemplate, Image, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.units import cm
from reportlab.lib.pagesizes import A4

from django.conf import settings

from stripe_subscription.models import StripeCustomer

STYLES = {'default': ParagraphStyle('default', fontSize=10)}

STYLES['text-center'] = ParagraphStyle('text-center',
                                       parent=STYLES['default'],
                                       alignment=TA_CENTER)

STYLES['text-right'] = ParagraphStyle('text-right',
                                      parent=STYLES['default'],
                                      alignment=TA_RIGHT)

STYLES['label'] = ParagraphStyle('label',
                                 parent=STYLES['default'],
                                 fontSize=8)

STYLES['header'] = ParagraphStyle('header',
                                  parent=STYLES['default'],
                                  fontSize=12)

STYLES['total'] = ParagraphStyle('total',
                                 parent=STYLES['default'],
                                 alignment=TA_CENTER,
                                 fontSize=16)

# For table paragraphs
styles = getSampleStyleSheet()
styleN = styles['BodyText']
styleN.alignment = TA_RIGHT
styleN.fontSize = 8


def draw_pdf(buffer, invoice):
    invoice_pdf = SimpleDocTemplate(buffer, pagesize=A4)
    parts = []
    parts.append(Paragraph(format_date(invoice.date), STYLES['text-right']))
    logo = os.path.join(settings.BASE_DIR2, 'static', 'Shopified-App2.png')
    parts.append(Image(logo, width=150, height=37, hAlign='LEFT'))
    customer = StripeCustomer.objects.get(customer_id=invoice.customer)
    data = [[header_paragraph(invoice), '', ],
            [invoice_id_paragraph(invoice), '', ],
            ['', ''],
            [invoicer_label(invoice), invoice_total_paragraph(invoice)],
            [invoicer_paragraph(invoice), invoice_due_paragraph(invoice)],
            ['', ''],
            [invoicee_label(invoice), ''],
            [invoicee_paragraph(customer), ''],
            ['', ''],
            [billing_period_label(invoice), ''],
            [billing_period_paragraph(invoice), '']]
    table = Table(data, colWidths=[10 * cm, 5 * cm])
    parts.append(table)
    parts.append(Spacer(1, 1 * cm))
    append_items_table(parts, invoice)
    parts.append(Spacer(1, 1 * cm))
    parts.append(Paragraph('<b>Thank you for your business!</b>', STYLES['text-center']))
    invoice_pdf.build(parts, onFirstPage=draw_footer)


def format_date(date):
    return date.strftime('%b. %d, %Y')


def draw_footer(canvas, doc):
    canvas.saveState()
    text = 'Questions? Email support@shopifiedapp.com'
    contact = Paragraph(text, STYLES['text-center'])
    w, h = contact.wrap(doc.width, doc.bottomMargin)
    contact.drawOn(canvas, doc.leftMargin, h)
    canvas.restoreState()


def header_paragraph(invoice):
    if invoice.paid:
        title = '<b>RECEIPT</b>'
    else:
        title = '<b>INVOICE</b>'
    return Paragraph(title, STYLES['header'])


def invoice_id_paragraph(invoice):
    if invoice.paid:
        source = invoice.charge.source
        title = 'Invoice ID: %s <br />Source: %s %s' % (invoice.id, source.brand, source.last4)
    else:
        title = 'Invoice ID: %s' % invoice.id
    return Paragraph(title, STYLES['default'])


def invoicer_label(invoice):
    invoicer_label = 'receipt' if invoice.paid else 'invoice'
    return Paragraph('%s FROM' % invoicer_label.upper(), STYLES['label'])


def invoice_total_paragraph(invoice):
    text = '<b>$%s %s</b>' % (str(invoice.total), invoice.currency.upper())
    return Paragraph(text, STYLES['total'])


def invoicer_paragraph(invoice):
    return Paragraph('Shopified App', STYLES['default'])


def invoice_due_paragraph(invoice):
    return Paragraph('Due on %s' % format_date(invoice.period_end), STYLES['text-center'])


def invoicee_label(invoice):
    return Paragraph('INVOICE TO', STYLES['label'])


def invoicee_paragraph(customer):
    invoice_to_company = customer.user.profile.get_config().get('invoice_to_company')
    if invoice_to_company:
        return company_paragraph(customer.user.profile)
    return Paragraph(customer.user.get_full_name(), STYLES['default'])


def company_paragraph(profile):
    br = '<br />'
    company = profile.company
    company_info = company.name

    street = get_address_line_string(company.address_line1, company.address_line2)
    if street:
        company_info += br
        company_info += street

    city_state = get_address_line_string(company.city, company.state, company.zip_code)
    if city_state:
        company_info += br
        company_info += city_state

    if company.country:
        company_info += br
        company_info += company.country

    return Paragraph(company_info, STYLES['default'])


def get_address_line_string(*args):
    line_items = [item for item in args if item]
    return ', '.join(line_items)


def billing_period_label(invoice):
    return Paragraph('BILLING PERIOD', STYLES['label'])


def billing_period_paragraph(invoice):
    start = format_date(invoice.period_start)
    end = format_date(invoice.period_end)
    text = '%s - %s' % (start, end)
    return Paragraph(text, STYLES['default'])


def append_items_table(parts, invoice):
    data = [['Description', 'Quantity', 'Amount']]
    append_item_rows(data, invoice)
    append_subtotal_row(data, invoice)
    append_discount_row(data, invoice)
    append_tax_row(data, invoice)
    append_total_row(data, invoice)
    append_amount_paid_row(data, invoice)
    table = Table(data, colWidths=[7 * cm, 5 * cm, 3 * cm])
    table.setStyle([('FONT', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('TEXTCOLOR', (0, 0), (-1, -1), (0.2, 0.2, 0.2)),
                    ('GRID', (0, 0), (-1, -2), 1, (0.9, 0.9, 0.9)),
                    ('GRID', (-2, -1), (-1, -1), 1, (0.9, 0.9, 0.9)),
                    ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                    ('BACKGROUND', (0, 0), (-1, 0), (0.9, 0.9, 0.9)), ])
    parts.append(table)
    return parts


def append_item_rows(data, invoice):
    for line in invoice.lines.get('data', []):
        if line.plan:
            description = line.description or line.plan.name
            quantity = line.quantity
        else:
            description = line.description
            quantity = ''
        amount = line.currency.upper() + ' ' + str(line.amount)
        data.append([Paragraph(description, styleN), quantity, amount])


def append_subtotal_row(data, invoice):
    subtotal = '%s %s' % (invoice.currency.upper(), str(invoice.subtotal))
    data.append(['', 'Subtotal', subtotal])


def append_discount_row(data, invoice):
    if invoice.discount:
        coupon = invoice.discount.coupon
        if coupon.amount_off:
            discount = '%s (%s %s off)' % (coupon.id,
                                           invoice.currency.upper(),
                                           invoice.discount_amount)
        else:
            discount = '%s (%s%% off)' % (coupon.id, coupon.percent_off)
        amount = '-%s %s' % (invoice.currency.upper(), str(invoice.discount_amount))
        data.append(['', Paragraph(discount, styleN), amount])


def append_tax_row(data, invoice):
    if invoice.tax:
        tax = invoice.currency.upper() + ' ' + str(invoice.tax)
        data.append(['', 'Tax', tax])


def append_total_row(data, invoice):
    total = invoice.currency.upper() + ' ' + str(invoice.total)
    data.append(['', 'Total', total])


def append_amount_paid_row(data, invoice):
    label = 'Amount paid' if invoice.paid else 'Amount due'
    label = Paragraph('<b>' + label + '</b>', styleN)
    amount = '$' + str(invoice.total) + ' ' + invoice.currency.upper()
    amount = Paragraph('<b>' + amount + '</b>', styleN)
    data.append(['', label, amount])
