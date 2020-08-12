import json

import factory
import factory.fuzzy


class PLSupplementFactory(factory.DjangoModelFactory):
    title = factory.fuzzy.FuzzyText()
    description = factory.fuzzy.FuzzyText()
    category = factory.fuzzy.FuzzyText()
    tags = factory.fuzzy.FuzzyText()
    shipstation_sku = factory.fuzzy.FuzzyText()
    cost_price = factory.fuzzy.FuzzyDecimal(0.1)
    product_type = factory.fuzzy.FuzzyText()
    wholesale_price = factory.fuzzy.FuzzyDecimal(0.1)
    label_template_url = factory.fuzzy.FuzzyText(prefix="http://", suffix=".com/image.jpeg")
    product_information = factory.fuzzy.FuzzyText()
    authenticity_certificate_url = factory.fuzzy.FuzzyText(prefix="http://", suffix=".com/image.jpeg")

    class Meta:
        model = 'supplements.PLSupplement'


class UserSupplementFactory(factory.DjangoModelFactory):
    title = factory.fuzzy.FuzzyText()
    description = factory.fuzzy.FuzzyText()
    category = factory.fuzzy.FuzzyText()
    tags = factory.fuzzy.FuzzyText()
    price = factory.fuzzy.FuzzyDecimal(0.1)

    class Meta:
        model = 'supplements.UserSupplement'


class UserSupplementLabelFactory(factory.DjangoModelFactory):
    url = factory.fuzzy.FuzzyText(prefix="http://", suffix=".com/image.jpeg")

    class Meta:
        model = 'supplements.UserSupplementLabel'


class LabelCommentFactory(factory.DjangoModelFactory):
    class Meta:
        model = 'supplements.LabelComment'


class PLSOrderFactory(factory.DjangoModelFactory):
    store_id = factory.fuzzy.FuzzyInteger(999)
    store_order_id = factory.fuzzy.FuzzyText()
    amount = factory.fuzzy.FuzzyInteger(999)
    sale_price = factory.fuzzy.FuzzyInteger(999)
    wholesale_price = factory.fuzzy.FuzzyInteger(999)

    class Meta:
        model = 'supplements.PLSOrder'


class PLSOrderLineFactory(factory.DjangoModelFactory):
    sku = factory.fuzzy.FuzzyText()
    shipstation_key = factory.fuzzy.FuzzyText()
    line_id = factory.fuzzy.FuzzyInteger(999)
    amount = factory.fuzzy.FuzzyInteger(999)
    sale_price = factory.fuzzy.FuzzyInteger(999)
    wholesale_price = factory.fuzzy.FuzzyInteger(999)

    class Meta:
        model = 'supplements.PLSOrderLine'


class LabelSizeFactory(factory.DjangoModelFactory):
    class Meta:
        model = 'supplements.LabelSize'


class MockupTypeFactory(factory.DjangoModelFactory):
    class Meta:
        model = 'supplements.MockupType'


class ShippingGroupFactory(factory.DjangoModelFactory):
    slug = factory.Iterator(['US', 'GB'])
    name = factory.Iterator(['United States', 'United Kingdom'])
    locations = factory.Iterator(['United States', 'United Kingdom'])
    immutable = True
    data = factory.Iterator([
        json.dumps({'shipping_cost_default': 30, 'shipping_rates': [{'weight_from': 0, 'weight_to': 10, 'shipping_cost': 3.34}]}),
        json.dumps({'shipping_cost_default': 50, 'shipping_rates': [{'weight_from': 0, 'weight_to': 10, 'shipping_cost': 6.56}]})
    ])

    class Meta:
        model = 'supplements.ShippingGroup'
