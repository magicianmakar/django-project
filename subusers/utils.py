
class AppURLConfig:
    namespace = ''
    prefix = ''

    def __init__(self, namespace):
        if namespace == 'chq':
            self.namespace = 'chq:'
            self.prefix = '/chq'
        elif namespace == 'woo':
            self.namespace = 'woo:'
            self.prefix = '/woo'
