(function() {
    'use strict';
    var vm = {task_id: null};
    var calculateSales = function() {
        if (!$('#sales').length) return;
        if (typeof(Pusher) === 'undefined') {
            toastr.error('This could be due to using Adblocker extensions<br>' +
                'Please whitelist Dropified website and reload the page<br>' +
                'Contact us for further assistance',
                'Pusher service is not loaded', {
                    timeOut: 0
                });
            return;
        }
        var pusher = new Pusher(sub_conf.key);
        var channel = pusher.subscribe(sub_conf.channel);

        
        channel.bind('sales-calculated', function(data) {
            if (vm.task_id === data.task) {
                $('#sales').show();
                $('#dropified').html(data['sales_dropified']);
                $('#dropified_commission').html(data['sales_dropified_commission']);
                $('#users').html(data['sales_users']);
                $('#users_commission').html(data['sales_users_commission']);
            }
        });

        var period = $('select[name=days]').val();
        if (!period) period = 0;

        $.ajax({
            url: '/api/calculate-sales',
            type: 'POST',
            data: JSON.stringify({
                period: parseInt(period),
            }),
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            success: function(data) {
                vm.task_id = data.task;
            },
            error: function(data) {
                displayAjaxError('Bulk Edit', data);
            }
        });
    };
    calculateSales();
})();