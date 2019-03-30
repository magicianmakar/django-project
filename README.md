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
Install `virtualenv` and `autoenv` modules first to setup a virtual environment:
```
sudo pip install virtualenv
sudo pip install autoenv
```

Then install the required modules:
```
cd dropified-webapp
virtualenv venv # add "-p python3" if necessary 
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
source .env
dj-migrate
```

### 4. Run tests
Automated tests will ensure the app is properly installed with all the required dependencies:
```
python manage.py test
```

We also have an alias for running tests
```
dj-test
```

This alias is equivalent to the following command:
```
dj-activate; python manage.py test -v 2 -k
```

We alss tag tests that are slow to run. This allows us to exclude the slow
tests like this:
```
dj-test --exclude-tag=slow
```

Slow tests are generally those that try to access external resources over HTTP.

### 5. Start the app
If the tests pass, start the application:

```
dj-run
```

App will be available at:
http://dev.dropified.com:8000

To register a new user account:
```
python manage.py createsuperuser
```

### Autoenv
Each time we enter dropified-webapp folder, `autoenv` will run the `.env` file, that will give us access to the following aliases:

|Command|Description|
|--|--|
|dj-run|Run web application server|
|dj-celery|Run Celery worker|
|dj-migrate|Run django Migrations on both databases|
|dj-makemigrations|python manage.py makemigrations|
|dj-shell|python manage.py shell_plus|
|dj-push|Run flake8 and push changes if flake8 doesn't raise any warnings|


### Docker based dev environment
You will need to install the following dependencies for this:
- Docker
- Docker Compose

Once the dependencies are installed, build applicaton image:
```
docker-compose build
```

Add the following lines to `.env.dev`:
```
export DATABASE_URL=postgres://postgres:@db:5432/shopified
export REDISCLOUD_URL="redis://redis:6379"
export REDISCLOUD_CACHE="redis://redis:6379"
export REDISCLOUD_ORDERS="redis://redis:6379"
alias dj-activate='echo "Empty dj-activate"'
alias dj-run='python manage.py runserver 0.0.0.0:8000'
```

Setup Docker docker environment:
```
./scripts/setup-docker
```

Log into the docker image:
```
docker-compose run --service-ports web
```

Run the application:
```
dj-run
```

You should be able to access the webapp at http://dev.dropified.com:8000/.

Docker runs the Celery worker automatically. You can connect to the log
output of the Celery worker by:
```
docker-compose logs -f celery
