from io import BytesIO
from urllib.request import urlopen

from django.utils import timezone

import requests
from pdfrw import PageMerge, PdfReader, PdfWriter
from pdfrw.pagemerge import RectXObj
from PIL import Image, ImageChops
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import Image as report_img
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

from stripe_subscription.invoices.pdf import STYLES, draw_footer


def get_elements(type):
    base_path = f'app/static/pls-mockup/{type}/'

    if type == 'bottle':
        bottle = Image.open(f'{base_path}bottle.png')
        mask = Image.open(f'{base_path}bottle_mask.png')
        shadow = Image.open(f'{base_path}bottle_shadows.png')
        base_shadow = Image.open(f'{base_path}base_shadow.png')
        light = Image.open(f'{base_path}bottle_highlights.png')

        return bottle, mask, shadow, base_shadow, light
    if type == 'container':
        container = Image.open(f'{base_path}container.png')
        mask = Image.open(f'{base_path}mask.png')
        shadow = Image.open(f'{base_path}shadow.png')
        light = Image.open(f'{base_path}reflections.png')

        return container, mask, shadow, light
    if type == 'tincture':
        bottle = Image.open(f'{base_path}tincture_bottle_30.png')
        mask = Image.open(f'{base_path}mask_30.png')
        shadow = Image.open(f'{base_path}shadows_30.png')
        light = Image.open(f'{base_path}reflections_30.png')
        dark = Image.open(f'{base_path}darken_30.png')

        return bottle, mask, shadow, light, dark


def get_group(base_mockup, mockup, dim, height, width, left_dim, right_dim, center_dim):
    left_mockup = base_mockup.copy()
    right_mockup = base_mockup.copy()

    center_mockup = Image.new('RGBA', (dim, dim))
    center_mockup.paste(mockup, center_dim)
    left_mockup = left_mockup.resize((height, width))
    right_mockup = right_mockup.resize((height, width))

    img = Image.new('RGBA', (dim, dim))
    img_2 = Image.new('RGBA', (dim, dim))
    img.paste(left_mockup, left_dim)
    img_2.paste(right_mockup, right_dim)

    img.alpha_composite(img_2)
    img.alpha_composite(center_mockup)

    return img


def get_group_of_3(base_mockup, type):
    height, width = base_mockup.size
    mockup = base_mockup.copy()

    if type == 'bottle':
        dim = 1000
        height = int(height * .8)
        width = int(width * .9)
        left_dim = (-190, 50)
        right_dim = (410, 50)
        center_dim = (10, 0)
    if type == 'container':
        dim = 1000
        height = int(height * .7)
        width = int(width * .9)
        left_dim = (-90, 70)
        right_dim = (500, 70)
        center_dim = (90, 20)
    if type == 'tincture':
        dim = 900
        height = int(height * .8)
        width = int(width * .9)
        left_dim = (-80, 50)
        right_dim = (260, 50)
        center_dim = (0, 0)

    return get_group(base_mockup, mockup, dim, height, width, left_dim, right_dim, center_dim)


def get_group_of_5(base_mockup, type):
    height, width = base_mockup.size
    group_of_3 = get_group_of_3(base_mockup, type)

    if type == 'bottle':
        dim = 1350
        height = int(height * .7)
        width = int(width * .8)
        left_dim = (-130, 340)
        right_dim = (840, 340)
        center_dim = (190, 220)
    if type == 'container':
        dim = 1350
        height = int(height * .6)
        width = int(width * .8)
        left_dim = (-50, 270)
        right_dim = (900, 270)
        center_dim = (180, 160)
    if type == 'tincture':
        dim = 900
        height = int(height * .7)
        width = int(width * .8)
        left_dim = (-180, 90)
        right_dim = (450, 90)
        center_dim = (0, 0)

    return get_group(base_mockup, group_of_3, dim, height, width, left_dim, right_dim, center_dim)


def get_bottle_mockup(label):
    def get_side_mockups(side, label):
        bottle, mask, shadow, base_shadow, light = get_elements('bottle')

        if side == 'front':
            width = 1547
            left_edge = 225
        else:
            width = 1852
            left_edge = -160

        dim = 1000
        size = (dim, dim)
        label_size = (int(width * 0.97), int(619 * 0.97))

        bottle_1 = bottle.resize(size)
        mask = mask.resize(size)

        label = label.resize(label_size)

        top_edge = -300
        right_edge = left_edge + dim
        bottom_edge = top_edge + dim

        label = label.crop((left_edge, top_edge, right_edge, bottom_edge))
        label.alpha_composite(shadow)

        bottle_2 = bottle_1.copy()

        shadow_mockup = Image.composite(label, bottle_1, mask)
        shadow_mockup.alpha_composite(light)
        bottle_1.alpha_composite(base_shadow)

        mockup = Image.composite(label, bottle_2, mask)
        shadow_mockup.alpha_composite(light)

        return shadow_mockup, mockup

    front_shadow_mockup, front_mockup = get_side_mockups('front', label)
    back_shadow_mockup, back_mockup = get_side_mockups('back', label)

    return {
        'front_shadow_mockup': front_shadow_mockup,
        'front_mockup': front_mockup,
        'back_shadow_mockup': back_shadow_mockup,
        'back_mockup': back_mockup,
        'group_of_3': get_group_of_3(front_shadow_mockup, 'bottle'),
        'group_of_5': get_group_of_5(front_shadow_mockup, 'bottle'),
    }


def get_container_mockup(label):
    def get_side_mockups(side, label):
        container, mask, shadow, light = get_elements('container')

        if side == 'front':
            width = 1856
            left_edge = 615
        else:
            width = 1550
            left_edge = -70

        dim = 860
        size = (dim, dim)
        label_size = (int(width * 0.97), int(495 * 0.97))

        container_1 = container.resize(size)
        mask = mask.resize(size)

        label = label.resize(label_size)

        top_edge = -250
        right_edge = left_edge + dim
        bottom_edge = top_edge + dim

        label = label.crop((left_edge, top_edge, right_edge, bottom_edge))

        container_2 = container_1.copy()

        container_1 = ImageChops.screen(container_1, light)
        shadow_mockup = Image.composite(label, container_1, mask)
        shadow_mockup.alpha_composite(shadow)

        container_2 = ImageChops.screen(container_2, light)
        mockup = Image.composite(label, container_2, mask)

        return shadow_mockup, mockup

    front_shadow_mockup, front_mockup = get_side_mockups('front', label)
    back_shadow_mockup, back_mockup = get_side_mockups('back', label)

    return {
        'front_shadow_mockup': front_shadow_mockup,
        'front_mockup': front_mockup,
        'back_shadow_mockup': back_shadow_mockup,
        'back_mockup': back_mockup,
        'group_of_3': get_group_of_3(front_shadow_mockup, 'container'),
        'group_of_5': get_group_of_5(front_shadow_mockup, 'container'),
    }


def get_tincture_mockup(label):
    def get_side_mockups(side, label):
        bottle, mask, shadow, light, dark = get_elements('tincture')

        if side == 'front':
            width = 877
            left_edge = 0
        else:
            width = 915
            left_edge = -230

        dim = 900
        size = (dim, dim)
        label_size = (int(width * 0.97), int(408 * 0.97))

        bottle_1 = bottle.resize(size)
        mask = mask.resize(size)
        label = label.resize(label_size)

        top_edge = -410
        right_edge = left_edge + dim
        bottom_edge = top_edge + dim
        label = label.crop((left_edge, top_edge, right_edge, bottom_edge))

        bottle_2 = bottle_1.copy()

        bottle_1.alpha_composite(light)
        shadow_mockup = Image.composite(label, bottle_1, mask)
        shadow_mockup.alpha_composite(dark)
        shadow_mockup.alpha_composite(shadow)

        bottle_2.alpha_composite(light)
        mockup = Image.composite(label, bottle_2, mask)
        mockup.alpha_composite(dark)

        return shadow_mockup, mockup

    front_shadow_mockup, front_mockup = get_side_mockups('front', label)
    back_shadow_mockup, back_mockup = get_side_mockups('back', label)

    return {
        'front_shadow_mockup': front_shadow_mockup,
        'front_mockup': front_mockup,
        'back_shadow_mockup': back_shadow_mockup,
        'back_mockup': back_mockup,
        'group_of_3': get_group_of_3(front_shadow_mockup, 'tincture'),
        'group_of_5': get_group_of_5(front_shadow_mockup, 'tincture'),
    }


def get_mockup(label, type):
    if type == 'bottle':
        return get_bottle_mockup(label)
    if type == 'container':
        return get_container_mockup(label)
    if type == 'tincture':
        return get_tincture_mockup(label)


def data_url_to_pil_image(url):
    data = BytesIO(urlopen(url).read())
    return Image.open(data)


def pil_to_fp(image):
    out = BytesIO()
    image.save(out, format='png')
    return out


def make_pdf_of(number):
    data = BytesIO()
    c = canvas.Canvas(data)
    c.drawString(0, 800, number)
    c.save()
    data.seek(0)

    reader = PdfReader(data)
    writer = PdfWriter()
    writer.addpage(reader.pages[0])
    blank_page = BytesIO()
    writer.write(blank_page)
    blank_page.seek(0)

    pdf = PdfReader(blank_page)
    pdf.pages[0].Rotate = 270
    pdf_pages = PageMerge() + pdf.pages

    return pdf_pages[0]


def get_order_number_label(item, use_latest=False):
    if use_latest:
        latest_label = item.label.user_supplement.labels.order_by('-created_at').first()
        label_url = latest_label.url if latest_label else item.label.url
    else:
        label_url = item.label.url

    order_number = item.pls_order.shipstation_order_number

    pdf_page = make_pdf_of(order_number)

    label_data = BytesIO(requests.get(label_url).content)
    base_label_pdf = PdfReader(label_data)

    page_merge = PageMerge(base_label_pdf.pages[0]).add(pdf_page)
    pdf_obj = page_merge[-1]
    pdf_obj.scale(0.3, 0.6)
    pdf_obj.x = 8
    pdf_obj.y = RectXObj(page_merge.page).h * 0.65

    page_merge.render()

    return base_label_pdf


def get_payment_pdf(order):
    data = BytesIO()
    date = timezone.now().strftime('%b %d, %Y')
    br = '<br />'

    order.user.authorize_net_customer.retrieve()
    profile = order.user.authorize_net_customer.payment_profile

    billing_address = (f'{profile["bill_to"].firstName} {profile["bill_to"].lastName} {br}'
                       f'{profile["bill_to"].address} {br}'
                       f'{profile["bill_to"].city}, {profile["bill_to"].state}, {profile["bill_to"].zip} {br}'
                       f'{profile["bill_to"].country}')

    pdf = SimpleDocTemplate(data, pagesize=A4)
    parts = []
    parts.append(Paragraph(date, STYLES['text-right']))
    logo = 'app/static/dropified-logo.png'
    parts.append(report_img(logo, width=150, height=37, hAlign='LEFT'))

    parts.append(Spacer(1, 1 * cm))
    parts.append(Paragraph('RECEIPT', STYLES['header']))
    parts.append(Spacer(1, .25 * cm))
    parts.append(Paragraph(f'Order # {order.order_number}', STYLES['default']))
    parts.append(Paragraph(f'Payment # {order.stripe_transaction_id}', STYLES['default']))

    parts.append(Spacer(1, .5 * cm))
    parts.append(Paragraph('RECEIPT FROM', STYLES['label']))
    parts.append(Paragraph(f'Dropified LLC{br}1430 Gadsden Hwy #116 #110, Birmingham, AL 35235', STYLES['default']))

    parts.append(Spacer(1, .5 * cm))
    parts.append(Paragraph('INVOICE TO', STYLES['label']))
    parts.append(Paragraph(billing_address, STYLES['default']))

    parts.append(Spacer(1, 1 * cm))
    line_data = [['Title', 'SKU', 'Price', 'Total']]
    for i in order.order_items.all():
        line_data.append([
            i.label.user_supplement.title,
            i.label.sku,
            f'{i.quantity} x ${i.label.user_supplement.cost_price}',
            "${:.2f}".format(i.amount / 100.),
        ])
    line_data.append(['', '', 'Sub Total', order.item_total])
    line_data.append(['', '', 'Shipping Cost', order.shipping_price_string])
    line_data.append(['', '', 'Total / Amount Paid', order.amount_string])
    table = Table(line_data, colWidths=[7 * cm, 5 * cm, 3 * cm])
    table.setStyle([('FONT', (0, 0), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('TEXTCOLOR', (0, 0), (-1, -1), (0.2, 0.2, 0.2)),
                    ('GRID', (0, 0), (-1, -2), 1, (0.9, 0.9, 0.9)),
                    ('GRID', (-2, -1), (-1, -1), 1, (0.9, 0.9, 0.9)),
                    ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                    ('BACKGROUND', (0, 0), (-1, 0), (0.9, 0.9, 0.9)), ])
    parts.append(table)

    paid_on = order.created_at.strftime('%b %d, %Y')
    parts.append(Spacer(1, .5 * cm))
    parts.append(Paragraph('PAID ON', STYLES['label']))
    parts.append(Paragraph(f'{paid_on}', STYLES['default']))

    parts.append(Spacer(1, 1 * cm))
    parts.append(Paragraph('<b>Thank you for your business!</b>', STYLES['text-center']))
    pdf.build(parts, onFirstPage=draw_footer)

    return data.getvalue()
