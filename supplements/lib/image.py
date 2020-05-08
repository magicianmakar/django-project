from io import BytesIO
from urllib.request import urlopen

import requests
from pdfrw import PageMerge, PdfReader, PdfWriter
from pdfrw.pagemerge import RectXObj
from PIL import Image, ImageChops
from reportlab.pdfgen import canvas


def get_bottle_mockup(label):
    base_path = 'app/static/pls-mockup/bottle/'

    bottle = Image.open(f'{base_path}bottle.png')
    mask = Image.open(f'{base_path}bottle_mask.png')
    shadow = Image.open(f'{base_path}bottle_shadows.png')
    base_shadow = Image.open(f'{base_path}base_shadow.png')
    light = Image.open(f'{base_path}bottle_highlights.png')

    dim = 1000
    size = (dim, dim)
    label_size = (int(1547 * 0.97), int(619 * 0.97))

    bottle = bottle.resize(size)
    mask = mask.resize(size)

    label = label.resize(label_size)

    left_edge = 300
    top_edge = -300
    right_edge = left_edge + dim
    bottom_edge = top_edge + dim

    label = label.crop((left_edge, top_edge, right_edge, bottom_edge))
    label.alpha_composite(shadow)

    mockup = Image.composite(label, bottle, mask)
    mockup.alpha_composite(light)
    bottle.alpha_composite(base_shadow)

    return mockup


def get_container_mockup(label):
    base_path = 'app/static/pls-mockup/container/'

    container = Image.open(f'{base_path}container.png')
    mask = Image.open(f'{base_path}mask.png')
    shadow = Image.open(f'{base_path}shadow.png')
    light = Image.open(f'{base_path}reflections.png')

    dim = 860
    size = (dim, dim)
    label_size = (int(1856 * 0.97), int(495 * 0.97))

    container = container.resize(size)
    mask = mask.resize(size)

    label = label.resize(label_size)

    left_edge = 500
    top_edge = -250
    right_edge = left_edge + dim
    bottom_edge = top_edge + dim

    label = label.crop((left_edge, top_edge, right_edge, bottom_edge))

    container = ImageChops.screen(container, light)
    mockup = Image.composite(label, container, mask)
    mockup.alpha_composite(shadow)

    return mockup


def get_tincture_mockup(label):
    base_path = 'app/static/pls-mockup/tincture/'

    bottle = Image.open(f'{base_path}tincture_bottle_30.png')
    mask = Image.open(f'{base_path}mask_30.png')
    shadow = Image.open(f'{base_path}shadows_30.png')
    light = Image.open(f'{base_path}reflections_30.png')
    dark = Image.open(f'{base_path}darken_30.png')

    dim = 900
    size = (dim, dim)
    label_size = (int(877 * 0.97), int(408 * 0.97))

    bottle = bottle.resize(size)
    mask = mask.resize(size)

    label = label.resize(label_size)

    left_edge = 0
    top_edge = -410
    right_edge = left_edge + dim
    bottom_edge = top_edge + dim

    label = label.crop((left_edge, top_edge, right_edge, bottom_edge))

    bottle.alpha_composite(light)
    mockup = Image.composite(label, bottle, mask)
    mockup.alpha_composite(dark)
    mockup.alpha_composite(shadow)

    return mockup


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


def get_order_number_label(item):
    order_number = item.pls_order.shipstation_order_number

    data = BytesIO()
    c = canvas.Canvas(data)
    c.drawString(0, 800, order_number)
    c.save()
    data.seek(0)

    reader = PdfReader(data)
    writer = PdfWriter()
    writer.addpage(reader.pages[0])
    pdf_data = BytesIO()
    writer.write(pdf_data)
    pdf_data.seek(0)

    pdf = PdfReader(pdf_data)
    pdf.pages[0].Rotate = 270
    pdf_pages = PageMerge() + pdf.pages
    pdf_page = pdf_pages[0]

    label_data = BytesIO(requests.get(item.label.url).content)
    base_label_pdf = PdfReader(label_data)

    page_merge = PageMerge(base_label_pdf.pages[0]).add(pdf_page)
    pdf_obj = page_merge[-1]
    pdf_obj.scale(0.5, 1)
    total_height = RectXObj(page_merge.page).h
    pdf_obj.y = total_height * .67

    page_merge.render()

    return base_label_pdf
