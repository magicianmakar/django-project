from io import BytesIO
from urllib.request import urlopen

import requests
from pdfrw import PageMerge, PdfReader, PdfWriter
from pdfrw.pagemerge import RectXObj
from PIL import Image
from reportlab.pdfgen import canvas


def wrap_image(bottle, label, mask, shadow, light, lighter):
    dim = 750
    size = (dim, dim)
    label_size = (int(1400 * 0.97), int(500 * 0.97))

    bottle = bottle.resize(size)
    mask = mask.resize(size)

    label = label.resize(label_size)

    left_edge = 325
    top_edge = -190
    right_edge = left_edge + dim
    bottom_edge = top_edge + dim

    label = label.crop((left_edge, top_edge, right_edge, bottom_edge))
    label.alpha_composite(shadow)

    mockup = Image.composite(label, bottle, mask)
    mockup.alpha_composite(light)
    mockup.alpha_composite(lighter)

    return mockup


def get_bottle_mockup(label):
    base_path = 'app/static/pls-mockup/'

    bottle = Image.open(f'{base_path}bottle_blank_mockup_750.png')
    mask = Image.open(f'{base_path}label_area_750.png')
    shadow = Image.open(f'{base_path}shadow_750.png')
    light = Image.open(f'{base_path}light_750.png')
    lighter = Image.open(f'{base_path}lighter_750.png')

    return wrap_image(bottle, label, mask, shadow, light, lighter)


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
