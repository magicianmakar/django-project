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
git clone git@github.com:ShopifiedApp/webapp.git
```

### 2. Virtual environment
Install `virtualenv` and `autoenv` modules first to setup a virtual environment:
```
sudo pip install virtualenv
sudo pip install autoenv
```

Then install the required modules:
```
cd shopified-webapp
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Database migration
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
dj-push: Run flake8 and push changes if flake8 doesn't raise any warnings
```

