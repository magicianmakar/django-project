import factory
import factory.fuzzy

from goals import step_slugs


class GoalFactory(factory.django.DjangoModelFactory):
    title = 'Add Products To Dropified Boards'
    # Clashes may occur because `goal_number` has a `unique` contraint
    goal_number = factory.fuzzy.FuzzyInteger(0, 9999)

    class Meta:
        model = 'goals.Goal'
        django_get_or_create = ('title',)


class StepFactory(factory.django.DjangoModelFactory):
    slug = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'goals.Step'
        django_get_or_create = ('slug',)


class GoalStepRelationshipFactory(factory.django.DjangoModelFactory):
    goal = factory.SubFactory(GoalFactory)
    step = factory.SubFactory(StepFactory)
    step_number = factory.fuzzy.FuzzyInteger(1, 999999)

    class Meta:
        model = 'goals.GoalStepRelationship'


class GoalWithStepsFactory(GoalFactory):
    step1 = factory.RelatedFactory(
        GoalStepRelationshipFactory,
        factory_related_name='goal',
        step__title='Save Product to Dropified',
        step__slug=step_slugs.SAVE_PRODUCT_TO_DROPIFIED
    )
    step2 = factory.RelatedFactory(
        GoalStepRelationshipFactory,
        factory_related_name='goal',
        step__title='Add Product to Board',
        step__slug=step_slugs.ADD_PRODUCT_TO_BOARD
    )
    step3 = factory.RelatedFactory(
        GoalStepRelationshipFactory,
        factory_related_name='goal',
        step__title='Install Chrome Extension',
        step__slug=step_slugs.INSTALL_CHROME_EXTENSION
    )
