$(document).ready(function(){
    new Cleave('#cc-number', {
        creditCard: true,
    });

    new Cleave('#cc-exp', {
        date: true,
        datePattern: ['m', 'Y']
    });

    $('#address_country').chosen({
        search_contains: true,
        width: '99%'
    });
});
