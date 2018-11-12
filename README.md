Dropified
===================

[app.dropified.com](https://app.dropified.com)

# Setup development environment

The following apps are required for Dropified:
- Python 2.7.11 or higher
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
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Database migration
Note: If you are running the app with PostgreSQL, you will probably need to
create the databases as well:

```
createdb --host=localhost -U postgres -O postgres -E utf8 -T template0 shopified
createdb --host=localhost -U postgres -O postgres -E utf8 -T template0 shopified-store
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
```
dj-run: Run web application server
dj-migrate: Run django Migrations on both databases
dj-makemigrations: python manage.py makemigrations
dj-shell: python manage.py shell
dj-celery: Run Celery worker
dj-push: Run flake8 and push changes if flake8 doesn't raise any warnings
```

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
export DATA_STORE_DATABASE_URL=postgres://postgres:@db:5432/shopified-store
export REDISCLOUD_URL="redis://redis:6379"
export REDISCLOUD_CACHE="redis://redis:6379"
export REDISCLOUD_ORDERS="redis://redis:6379"
alias dj-run='dj-activate; python manage.py runserver 0.0.0.0:8000'
```

Log into the docker image:
```
docker-compose run -p 8000:8000 web
```

Create databases if you are logging in for the first time:
```
createdb --host=db -U postgres -O postgres -E utf8 -T template0 shopified
createdb --host=db -U postgres -O postgres -E utf8 -T template0 shopified-store
```

Run the application:
```
dj-migrate
dj-run
```

You should be able to access the webapp at http://dev.dropified.com:8000/.

To run the celery workers, start a new terminal session of webapp:
```
docker-compose run web
```

Start the worker:
```
export C_FORCE_ROOT=1
dj-celery
```
