import requests


def start_test(resource_url):
    url = ('http://localhost:8000/dropified_product/'
           'shipstation/webhook/order_shipped')
    data = {
        'resource_url': resource_url,
        'event': 'SHIP_NOTIFY'}
    response = requests.post(url, json=data)
    print(response.status_code)


if __name__ == '__main__':
    resource_url = ("https://my-json-server.typicode.com"
                    "/umairwaheed/shipstation-test/shipments")
    start_test(resource_url)
