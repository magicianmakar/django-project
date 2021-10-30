import json


class WooAPIDataMixin:
    @property
    def parsed(self):
        try:
            return json.loads(self.data)
        except:
            return {}

    def update_data(self, data):
        if type(data) is not dict:
            data = json.loads(data)

        try:
            product_data = json.loads(self.data)
        except:
            product_data = {}

        product_data.update(data)

        self.data = json.dumps(product_data)
