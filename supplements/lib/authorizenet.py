import re
from decimal import Decimal

from django.conf import settings

from authorizenet import apicontractsv1
from authorizenet.apicontrollers import (
    createCustomerPaymentProfileController,
    createCustomerProfileController,
    createTransactionController,
    getCustomerPaymentProfileController,
    getTransactionDetailsController,
)
from authorizenet.constants import constants

from lib.exceptions import capture_message


def to_price(price):
    return "{:.2f}".format(price / 100)


def get_merchant_auth():
    merchant_auth = apicontractsv1.merchantAuthenticationType()
    merchant_auth.name = settings.AUTH_NET_LOGIN_ID
    merchant_auth.transactionKey = settings.AUTH_NET_TRANSACTION_KEY
    return merchant_auth


def create_customer_profile(user):
    create_profile = apicontractsv1.createCustomerProfileRequest()
    create_profile.merchantAuthentication = get_merchant_auth()

    user_id = str(user.id)
    name = user.get_full_name()
    email = user.email

    profile = apicontractsv1.customerProfileType(user_id, name, email)
    create_profile.profile = profile

    controller = createCustomerProfileController(create_profile)
    if settings.AUTH_NET_PROD:
        controller.setenvironment(constants.PRODUCTION)

    controller.execute()

    response = controller.getresponse()

    duplicate_regex = r'A duplicate record with ID (\d+) already exists.'
    if response.messages.resultCode == 'Ok':
        return response.customerProfileId

    message = response.messages.message[0]['text'].text
    result = re.match(duplicate_regex, message)
    if result:
        return result.group(1)
    else:
        raise Exception(message)


def create_payment_profile(payment_data, customer_profile_id):
    credit_card = apicontractsv1.creditCardType()
    credit_card.cardNumber = payment_data['cc_number']
    credit_card.expirationDate = payment_data['cc_expiry']
    credit_card.cardCode = payment_data['cc_cvv']

    payment = apicontractsv1.paymentType()
    payment.creditCard = credit_card

    name = payment_data['name']
    name = name.split()

    first_name = name[0]
    last_name = ' '.join(name[1:])

    bill_to = apicontractsv1.customerAddressType()
    bill_to.firstName = first_name
    bill_to.lastName = last_name

    address1 = payment_data['address_line1']
    address2 = payment_data['address_line2']
    bill_to.address = address1 + ' ' + address2

    bill_to.city = payment_data['address_city']
    bill_to.state = payment_data['address_state']
    bill_to.zip = payment_data['address_zip']
    bill_to.country = payment_data['address_country']

    profile = apicontractsv1.customerPaymentProfileType()
    profile.payment = payment
    profile.billTo = bill_to

    create_profile = apicontractsv1.createCustomerPaymentProfileRequest()
    create_profile.merchantAuthentication = get_merchant_auth()
    create_profile.paymentProfile = profile
    create_profile.customerProfileId = str(customer_profile_id)
    create_profile.validationMode = 'liveMode'

    controller = createCustomerPaymentProfileController(create_profile)
    if settings.AUTH_NET_PROD:
        controller.setenvironment(constants.PRODUCTION)

    controller.execute()

    response = controller.getresponse()
    error = ''
    duplicate_regex = r'A duplicate customer payment profile already exists.'
    if response.messages.resultCode == 'Ok':
        return (response.customerPaymentProfileId, error)

    error = response.messages.message[0]['text'].text
    result = re.match(duplicate_regex, error)
    if result:
        return (response.customerPaymentProfileId, '')

    capture_message(error, level='warning')
    return ('', error)


def charge_customer_profile(amount, customer_id, payment_id, line):
    transaction_id = None

    profile_to_charge = apicontractsv1.customerProfilePaymentType()
    profile_to_charge.customerProfileId = customer_id
    profile_to_charge.paymentProfile = apicontractsv1.paymentProfile()
    profile_to_charge.paymentProfile.paymentProfileId = payment_id

    transaction_request = apicontractsv1.transactionRequestType()
    transaction_request.transactionType = "authCaptureTransaction"
    transaction_request.amount = to_price(amount)
    transaction_request.profile = profile_to_charge

    line_items = apicontractsv1.ArrayOfLineItem()

    assert len(line['name']) < 31
    line_item = apicontractsv1.lineItemType()
    line_item.itemId = str(line['id'])
    line_item.name = line['name']
    line_item.quantity = line['quantity']
    line_item.unitPrice = to_price(line['unit_price'])
    line_items.lineItem.append(line_item)

    transaction_request.lineItems = line_items

    # Add values for transaction settings
    duplicateWindowSetting = apicontractsv1.settingType()
    duplicateWindowSetting.settingName = "duplicateWindow"
    duplicateWindowSetting.settingValue = "0"
    transSetting = apicontractsv1.ArrayOfSetting()
    transSetting.setting.append(duplicateWindowSetting)
    transaction_request.transactionSettings = transSetting

    create_transaction = apicontractsv1.createTransactionRequest()
    create_transaction.merchantAuthentication = get_merchant_auth()
    create_transaction.transactionRequest = transaction_request

    controller = createTransactionController(create_transaction)
    if settings.AUTH_NET_PROD:
        controller.setenvironment(constants.PRODUCTION)

    controller.execute()

    response = controller.getresponse()

    # https://developer.authorize.net/api/reference/index.html#payment-transactions-charge-a-customer-profile
    errors = []
    if response.messages.resultCode == "Ok":
        if hasattr(response.transactionResponse, 'messages'):
            transaction_id = response.transactionResponse.transId
        else:
            if hasattr(response.transactionResponse, 'errors'):
                for error in response.transactionResponse.errors.error:
                    errors.append(f"{error.errorCode}: {error.errorText}")
    else:
        if hasattr(response, 'transactionResponse') and hasattr(response.transactionResponse, 'errors'):
            for error in response.transactionResponse.errors.error:
                errors.append(f"{error.errorCode}: {error.errorText}")
        else:
            for error in response.messages.message:
                errors.append(f"{error['code'].text}: {error['text'].text}")

    if errors:
        capture_message('Auth.NET transaction error', extra={'authnet-errors': errors})

    return transaction_id, errors


def get_transaction_errors(response):
    errors = []
    # https://developer.authorize.net/api/reference/index.html#payment-transactions-charge-a-customer-profile
    if hasattr(response, 'transactionResponse') and hasattr(response.transactionResponse, 'errors'):
        for error in response.transactionResponse.errors.error:
            errors.append(f"{error.errorCode}: {error.errorText}")
    else:
        for error in response.messages.message:
            errors.append(f"{error['code'].text}: {error['text'].text}")
    return errors


def charge_customer_for_items(transaction, items):
    total_amount = Decimal('0.0')
    transaction_id = None
    errors = []

    if len(items) > 30:
        total_amount = sum(item['amount'] * item['quantity'] for item in items)
    else:
        line_items = apicontractsv1.ArrayOfLineItem()
        for item in items:
            total_amount += item['amount'] * item['quantity']

            assert len(item['name']) < 31
            line_item = apicontractsv1.lineItemType()
            line_item.itemId = str(item['id'])
            line_item.name = item['name']
            line_item.quantity = item['quantity']
            line_item.unitPrice = str(item['amount'])
            line_items.lineItem.append(line_item)

        transaction.lineItems = line_items

        # Add values for transaction settings
        duplicateWindowSetting = apicontractsv1.settingType()
        duplicateWindowSetting.settingName = "duplicateWindow"
        duplicateWindowSetting.settingValue = "0"
        transSetting = apicontractsv1.ArrayOfSetting()
        transSetting.setting.append(duplicateWindowSetting)
        transaction.transactionSettings = transSetting

    if len(items) > 1:
        order_description = f"Processing Orders between #{items[0]['id']} - #{items[-1]['id']}"
    else:
        order_description = f"Processing Order #{items[0]['id']}"
    order = apicontractsv1.orderType()
    order.description = order_description
    transaction.order = order
    transaction.amount = str(total_amount)

    request = apicontractsv1.createTransactionRequest()
    request.merchantAuthentication = get_merchant_auth()
    request.transactionRequest = transaction

    controller = createTransactionController(request)
    if settings.AUTH_NET_PROD:
        controller.setenvironment(constants.PRODUCTION)

    controller.execute()
    response = controller.getresponse()
    if response.messages.resultCode == "Ok" and hasattr(response.transactionResponse, 'messages'):
        transaction_id = response.transactionResponse.transId

    errors = get_transaction_errors(response)
    if errors:
        capture_message('Auth.NET transaction error', extra={'authnet-errors': errors})

    return transaction_id, errors[0]


def refund_customer_profile(amount, customer_id, payment_id, trans_id):
    profile_to_charge = apicontractsv1.customerProfilePaymentType()
    profile_to_charge.customerProfileId = customer_id
    profile_to_charge.paymentProfile = apicontractsv1.paymentProfile()
    profile_to_charge.paymentProfile.paymentProfileId = payment_id

    transaction_request = apicontractsv1.transactionRequestType()
    transaction_request.transactionType = "refundTransaction"
    transaction_request.amount = amount
    transaction_request.refTransId = trans_id
    transaction_request.profile = profile_to_charge

    create_transaction = apicontractsv1.createTransactionRequest()
    create_transaction.merchantAuthentication = get_merchant_auth()
    create_transaction.transactionRequest = transaction_request

    controller = createTransactionController(create_transaction)
    if settings.AUTH_NET_PROD:
        controller.setenvironment(constants.PRODUCTION)

    controller.execute()

    response = controller.getresponse()

    return get_authnet_response(response)


def void_unsettled_transaction(trans_id):
    transaction_request = apicontractsv1.transactionRequestType()
    transaction_request.transactionType = "voidTransaction"
    transaction_request.refTransId = trans_id

    create_transaction = apicontractsv1.createTransactionRequest()
    create_transaction.merchantAuthentication = get_merchant_auth()
    create_transaction.transactionRequest = transaction_request

    controller = createTransactionController(create_transaction)
    if settings.AUTH_NET_PROD:
        controller.setenvironment(constants.PRODUCTION)

    controller.execute()

    response = controller.getresponse()
    return get_authnet_response(response)


def retrieve_transaction_status(trans_id):
    transaction_status = None

    transactionDetailsRequest = apicontractsv1.getTransactionDetailsRequest()
    transactionDetailsRequest.merchantAuthentication = get_merchant_auth()
    transactionDetailsRequest.transId = trans_id

    controller = getTransactionDetailsController(transactionDetailsRequest)
    if settings.AUTH_NET_PROD:
        controller.setenvironment(constants.PRODUCTION)

    controller.execute()
    transactionDetailsResponse = controller.getresponse()

    if transactionDetailsResponse is not None:
        if transactionDetailsResponse.messages.resultCode == apicontractsv1.messageTypeEnum.Ok:
            transaction_status = transactionDetailsResponse.transaction.transactionStatus

    return transaction_status


def get_authnet_response(response):
    transaction_id = None
    errors = []
    if response.messages.resultCode == "Ok":
        if hasattr(response.transactionResponse, 'messages'):
            transaction_id = response.transactionResponse.transId
        else:
            if hasattr(response.transactionResponse, 'errors'):
                for error in response.transactionResponse.errors.error:
                    errors.append(f"{error.errorCode}: {error.errorText}")
    else:
        if hasattr(response, 'transactionResponse') and hasattr(response.transactionResponse, 'errors'):
            for error in response.transactionResponse.errors.error:
                errors.append(f"{error.errorCode}: {error.errorText}")
        else:
            for error in response.messages.message:
                errors.append(f"{error['code'].text}: {error['text'].text}")

    if errors:
        capture_message('Auth.NET transaction error', extra={'authnet-errors': errors})

    return transaction_id, errors


def get_customer_payment_profile(profile_id, payment_id):
    get_profile = apicontractsv1.getCustomerPaymentProfileRequest()
    get_profile.merchantAuthentication = get_merchant_auth()
    get_profile.customerProfileId = profile_id
    get_profile.customerPaymentProfileId = payment_id

    controller = getCustomerPaymentProfileController(get_profile)
    if settings.AUTH_NET_PROD:
        controller.setenvironment(constants.PRODUCTION)

    controller.execute()

    response = controller.getresponse()

    return response.paymentProfile
