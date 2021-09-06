import os
import yaml


def read_file(fname):
    if os.path.isfile(fname):
        with open(fname) as infile:
            config = yaml.load(infile, Loader=yaml.FullLoader)
            environment = config.get('environment')
            if type(environment) is dict:
                for key, val in environment.items():
                    if val is None:
                        val = ''
                    elif type(val) is not str:
                        val = str(val)

                    os.environ[key] = val


def setup_env():
    if not os.environ.get('SHOPIFY_API_KEY'):
        read_file('env.yaml')
        read_file('env.dev.yaml')
