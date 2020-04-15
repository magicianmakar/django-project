import re

from django.conf import settings

from authorizenet import apicontractsv1
from authorizenet.apicontrollers import (
    createCustomerPaymentProfileController,
    createCustomerProfileController,
    createTransactionController,
    getCustomerPaymentProfileController
)
from raven.contrib.django.raven_compat.models import client as raven_client


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
    controller.execute()

    response = controller.getresponse()
    error = ''
    if response.messages.resultCode == 'Ok':
        return (response.customerPaymentProfileId, error)

    error = message = response.messages.message[0]['text']
    raven_client.captureMessage(message, level='warning')
    return ('', error)


def charge_customer_profile(amount, customer_id, payment_id, lines):
    profile_to_charge = apicontractsv1.customerProfilePaymentType()
    profile_to_charge.customerProfileId = customer_id
    profile_to_charge.paymentProfile = apicontractsv1.paymentProfile()
    profile_to_charge.paymentProfile.paymentProfileId = payment_id

    transaction_request = apicontractsv1.transactionRequestType()
    transaction_request.transactionType = "authCaptureTransaction"
    transaction_request.amount = to_price(amount)
    transaction_request.profile = profile_to_charge

    line_items = apicontractsv1.ArrayOfLineItem()

    for line in lines:
        assert len(line['name']) < 31
        line_item = apicontractsv1.lineItemType()
        line_item.itemId = str(line['line_id'])
        line_item.name = line['name']
        line_item.quantity = line['quantity']
        line_item.unitPrice = to_price(line['unit_price'])
        line_items.lineItem.append(line_item)

    transaction_request.lineItems = line_items

    create_transaction = apicontractsv1.createTransactionRequest()
    create_transaction.merchantAuthentication = get_merchant_auth()
    create_transaction.transactionRequest = transaction_request

    controller = createTransactionController(create_transaction)
    controller.execute()

    response = controller.getresponse()

    if hasattr(response.transactionResponse, 'messages'):
        return response.transactionResponse.transId


def get_customer_payment_profile(profile_id, payment_id):
    get_profile = apicontractsv1.getCustomerPaymentProfileRequest()
    get_profile.merchantAuthentication = get_merchant_auth()
    get_profile.customerProfileId = profile_id
    get_profile.customerPaymentProfileId = payment_id

    controller = getCustomerPaymentProfileController(get_profile)
    controller.execute()

    response = controller.getresponse()

    return response.paymentProfile
