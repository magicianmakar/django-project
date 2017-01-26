hopified App Website #

[app.shopifiedapp.com](https://app.shopifiedapp.com)

# Setup developement envirement

The following apps are required for Shopified App:
- Python 2.7.11 or higher
- Python Pip
- PostgreSQL 9.5
- Redis Server 3.0

### Clone Repository
```
git clone git@gitlab.com:shopifiedapp/shopified-webapp.git
```

### Virtual envirement
We need to install `virtualenv` and `autoenv` modules first to setup a virtual envirement:
```
sudo pip install virtualenv
sudo pip install autoenv
```

Then we install the required modules:
```
cd shopified-webapp
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Database migration
```
source .env
dj-migrate
```

### Run tests
Automatted tests will ensure the app is properly installed with all the required dependencies:
```
python manage.py test
```

### Start the app
if the tests pass, we can start the application:

```
dj-run
```

App will be available at:
http://127.0.0.1:8000

To register a new user account:
```
python manage.py createsuperuser
```

### Autoenv
Each time we enter shopified-webapp folder, `autoenv` will run the `.env` file, that will give us access to the following aliases:
```
dj-run: Run web application server
dj-migrate: Run django Migrations on both databases
dj-makemigrations: python manage.py makemigrations
dj-shell: python manage.py shell
dj-celery: Run Celery worker
dj-push: Run flake8 and push chnages if flake8 doesn't return any warnings
```

