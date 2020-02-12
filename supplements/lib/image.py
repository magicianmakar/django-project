from io import BytesIO
from urllib.request import urlopen

from PIL import Image


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
