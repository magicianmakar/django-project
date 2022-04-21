import factory
import factory.fuzzy


class VideosListFactory(factory.django.DjangoModelFactory):
    user = factory.SubFactory('leadgalaxy.tests.factories.UserFactory')
    title = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'youtube_ads.VideosList'
