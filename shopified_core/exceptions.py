
class ApiLoginException(Exception):
    def description(self):
        if str(self) == 'unvalid_access_token':
            return ('Unvalide Access Token.\nMake sure you are logged-in '
                    'before using Chrome Extension')

        elif str(self) == 'different_account_login':
            return ('You are logged in with different accounts, '
                    'please use the same account in the Extension and Shopified Web app')

        elif str(self) == 'login_required':
            return ('Unauthenticated API call. \nMake sure you are logged-in '
                    'before using Chrome Extension')

        else:
            return 'Unknown Login Error'


class ApiProcessException(Exception):
    pass


class ProductExportException(Exception):
    pass


class AliexpressFulfillException(Exception):
    pass


class RedirectException(Exception):
    def __init__(self, url):
        self.url = url
