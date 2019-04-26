import factory
import factory.fuzzy


class GoalFactory(factory.DjangoModelFactory):
    title = factory.fuzzy.FuzzyText()
    # Clashes may occur because `goal_number` has a `unique` contraint
    goal_number = factory.fuzzy.FuzzyInteger(0, 9999)

    class Meta:
        model = 'goals.Goal'


class StepFactory(factory.DjangoModelFactory):
    slug = factory.fuzzy.FuzzyText()

    class Meta:
        model = 'goals.Step'
