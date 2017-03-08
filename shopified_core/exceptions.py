
class ApiLoginException(Exception):
    def description(self):
        if self.message == 'unvalid_access_token':
            return ('Unvalide Access Token.\nMake sure you are logged-in '
                    'before using Chrome Extension')

        elif self.message == 'different_account_login':
            return ('You are logged in with different accounts, '
                    'please use the same account in the Extension and Shopified Web app')

        elif self.message == 'login_required':
            return ('Unauthenticated API call. \nMake sure you are logged-in '
                    'before using Chrome Extension')

        else:
            return 'Unknown Login Error'


class ProductExportException(Exception):
    pass
