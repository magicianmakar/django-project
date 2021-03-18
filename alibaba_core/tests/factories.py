import factory


class AlibabaAccountFactory(factory.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    access_token = factory.fuzzy.FuzzyText()
    alibaba_user_id = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'alibaba_core.AlibabaAccount'
