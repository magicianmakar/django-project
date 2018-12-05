(function() {
    'use strict';
    $("#q").autocomplete({
        serviceUrl: '/tubehunt/autocomplete',
        dataType: 'json',
        paramName: 'q',
        minLength: 1,
        transformResult: function(response) {
            return {
                suggestions: $.map(response, function(dataItem) {
                    return { value: dataItem, data: dataItem };
                })
            };
        }
    });
})();
