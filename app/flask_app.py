from flask import Flask, request
from flask.ext.sqlalchemy import SQLAlchemy
import os

def get_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://app1spee_usr1:FXwr4scETfLY@app1.speedaudits.com/app1spee_crawler'
    db = SQLAlchemy(app)

    return app, db

app, db = get_app()

class WebsiteImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    src = db.Column(db.String(256))
    alt = db.Column(db.String(300))

    website_link_id = db.Column(db.Integer, db.ForeignKey('website_link.id'))
    website_link = db.relationship('WebsiteLink', backref=db.backref('images', lazy='dynamic'))

    def __init__(self, src, alt, link):
        self.src = src
        self.alt = alt
        self.website_link = link

    def __repr__(self):
        return '<Image %r>' % self.src

class WebsiteLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(256))
    title = db.Column(db.String(300))
    status = db.Column(db.Integer)
    description = db.Column(db.String(500))

    website_id = db.Column(db.Integer, db.ForeignKey('website.id'))
    website = db.relationship('Website', backref=db.backref('links', lazy='dynamic'))

    def __init__(self, url, title, status, description, website):
        self.url = url
        self.title = title
        self.status = status
        self.description = description

        self.website = website

    def __repr__(self):
        return '<Link %r>' % self.title

class Website(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(256))
    title = db.Column(db.String(300))
    status = db.Column(db.Integer)
    callback_url = db.Column(db.String(300))

    def __init__(self, url, title, status, callback=''):
        self.url = url
        self.title = title
        self.status = status
        self.callback_url = callback

    def __repr__(self):
        return '<Website %r>' % self.title


def create_tables():
    db.create_all()
    db.session.commit()
