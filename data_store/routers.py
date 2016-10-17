

class DataStoreRouter(object):
    app_label = 'data_store'
    db_label = 'store_db'

    def db_for_read(self, model, **hints):
        if model._meta.app_label == self.app_label:
            return self.db_label
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == self.app_label:
            return self.db_label
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == self.db_label:
            return app_label == self.app_label
        return None
