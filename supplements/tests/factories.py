import factory
import factory.fuzzy


class PLSupplementFactory(factory.DjangoModelFactory):
    class Meta:
        model = 'supplements.PLSupplement'


class UserSupplementFactory(factory.DjangoModelFactory):
    class Meta:
        model = 'supplements.UserSupplement'


class UserSupplementLabelFactory(factory.DjangoModelFactory):
    class Meta:
        model = 'supplements.UserSupplementLabel'


class LabelCommentFactory(factory.DjangoModelFactory):
    class Meta:
        model = 'supplements.LabelComment'


class PLSOrderFactory(factory.DjangoModelFactory):
    amount = factory.fuzzy.FuzzyInteger(999)
    sale_price = factory.fuzzy.FuzzyInteger(999)
    wholesale_price = factory.fuzzy.FuzzyInteger(999)

    class Meta:
        model = 'supplements.PLSOrder'


class PLSOrderLineFactory(factory.DjangoModelFactory):
    amount = factory.fuzzy.FuzzyInteger(999)
    sale_price = factory.fuzzy.FuzzyInteger(999)
    wholesale_price = factory.fuzzy.FuzzyInteger(999)

    class Meta:
        model = 'supplements.PLSOrderLine'
