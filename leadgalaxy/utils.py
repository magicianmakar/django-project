import re, json, requests, arrow

def get_shopify_order_note(store, order_id):
    rep = requests.get(store.get_link('/admin/orders/{}.json'.format(order_id), api=True)).json()
    return rep['order']['note']

def set_shopify_order_note(store, order_id, note):
    rep = requests.put(
        url=store.get_link('/admin/orders/{}.json'.format(order_id), api=True),
        json={
            'order': {
                'id': order_id,
                'note': note
            }
        }
    ).json()

    return rep['order']['id'] == order_id

def add_shopify_order_note(store, order_id, new_note):
    note = get_shopify_order_note(store, order_id)

    if note:
        note = '{}\n{}'.format(note, new_note)
    else:
        note = new_note

    return set_shopify_order_note(store, order_id, note)
