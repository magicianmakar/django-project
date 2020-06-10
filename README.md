[Dropified](https://app.dropified.com)  [![CircleCI](https://circleci.com/gh/TheDevelopmentMachine/dropified-webapp.svg?style=svg&circle-token=c324db3902d470903436fe6f8628bae274a6aeaf)](https://circleci.com/gh/TheDevelopmentMachine/dropified-webapp)
===================

# Setup development environment

The following apps are required for Dropified:
- Python 3.6
- Python Pip
- PostgreSQL 9.5
- Redis Server 3.0

### 1. Clone repository
```
git clone git@github.com:TheDevelopmentMachine/dropified-webapp.git
```

### 2. Virtual environment
Install `virtualenv` to setup a virtual environment:
```
sudo pip install virtualenv
```

Then install the required modules:
```
cd dropified-webapp
virtualenv venv -p python3

source venv/bin/activate

pip install -r requirements.txt
```

### 3. Database migration
Note: If you are running the app with PostgreSQL, you will probably need to
create the databases as well:

```
createdb --host=localhost -U postgres -O postgres -E utf8 -T template0 shopified
```

Run the migrations:
```
python manage.py migrate
```

### 4. Run tests
Automated tests will ensure the app is properly installed with all the required dependencies:
```
python manage.py test
```

For a testing a single test case, we can do:
```
python manage.py test -n home.tests.test_goto_page.GotoPageTestCase.test_shopify
```

We also tag tests that are slow to run. This allows us to exclude the slow
tests like this:
```
manage.py test -n --exclude-tag=slow
```

Slow tests are generally those that try to access external resources over HTTP.

### 5. Start the app
If the tests pass, start the application:

```
python manage.py runserver
```

App will be available at:
http://dev.dropified.com:8000

To register a new user account:
```
python manage.py createsuperuser
```

### pre-commit tool
pre-commit is a tool that can verify your code before you push it to Github (or before git commit)
Installing it is simple, run pip install outside of virtualenv enviroment:
```sudo pip install pre-commit```
Then go to Dropified webapp and install git hooks
```pre-commit install```
Now you can use git as usual
You can find more about this tool in here [pre-commit.com](https://pre-commit.com)

### Docker based dev environment
You will need to install the following dependencies for this:
- Docker
- Docker Compose

Once the dependencies are installed, build applicaton image:
```
cd docker
docker-compose build
```

Add the following lines to `env.dev.yaml`:
```
environment:
  DATABASE_URL: postgres://postgres:@db:5432/shopified
  REDISCLOUD_URL: redis://redis:6379
  REDISCLOUD_CACHE: redis://redis:6379
  REDISCLOUD_ORDERS: redis://redis:6379
```

Setup Docker docker environment:
```
cd docker
../scripts/setup-docker
```

Log into the docker image:
```
cd docker
docker-compose run --service-ports web
```

Run the application:
```
python manage.py runserver 0.0.0.0:8000
```

You should be able to access the webapp at http://dev.dropified.com:8000/.

Docker runs the Celery worker automatically. You can connect to the log
output of the Celery worker by:
```
docker-compose logs -f celery
```
