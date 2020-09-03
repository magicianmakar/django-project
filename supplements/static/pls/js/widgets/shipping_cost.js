var loadedShipping = false;
document.addEventListener("DOMContentLoaded", function() {
    function addShippingRule(data) {
        data = typeof(data) !== 'undefined' ? data : {};
        var ruleTemplate = Handlebars.compile(document.getElementById('shipping-rule-template').innerHTML);
        var wrapper = document.createElement('div');
        wrapper.innerHTML = ruleTemplate(data);
        var ruleElement = wrapper.firstElementChild;
        ruleElement.querySelector('.close').addEventListener('click', function(e) {
            e.preventDefault();
            ruleElement.remove();
        });
        return ruleElement;
    }

    function getShippingService(data) {
        data = typeof(data) !== 'undefined' ? data : {};

        var serviceElement;
        if (data.service_id) {
            serviceElement = document.getElementById(data.service_id);
            if (serviceElement) {
                return serviceElement;
            }
        } else {
            var lastService = document.querySelector('#shipping-services fieldset:last-child');
            var lastServiceId = 1;
            if (lastService) {
                lastServiceId = parseInt(lastService.getAttribute('id').replace('shipping-service-', '')) + 1;
            }
            data.service_id = 'shipping-service-' + lastServiceId;
        }

        var serviceTemplate = Handlebars.compile(document.getElementById('shipping-service-template').innerHTML);
        var wrapper = document.createElement('div');
        wrapper.innerHTML = serviceTemplate(data);

        serviceElement = wrapper.firstElementChild;
        serviceElement.querySelector('.add-link').addEventListener('click', function(e) {
            e.preventDefault();

            serviceElement.appendChild(addShippingRule());
        });
        return serviceElement;
    }

    var servicesElement = document.getElementById('shipping-services');
    var shippingGroupData = document.querySelector('#shipping-services-field [type="hidden"]').value;
    if (shippingGroupData) {
        shippingGroupData = JSON.parse(shippingGroupData);
        document.getElementsByClassName('shipping_cost_default')[0].value = shippingGroupData.shipping_cost_default;
        if (shippingGroupData.services) {
            shippingGroupData.services.forEach(function(service) {
                servicesElement.appendChild(getShippingService(service));
            });
        } else {
            servicesElement.appendChild(getShippingService());
        }

        shippingGroupData.shipping_rates.forEach(function(rule) {
            var shippingRule = addShippingRule(rule);
            var serviceElement;

            if (rule.service_id) {
                serviceElement = getShippingService(rule);
            } else {
                serviceElement = document.querySelector('#shipping-services fieldset:first-child');
            }
            serviceElement.appendChild(shippingRule);
        });
    }
    loadedShipping = true;

    document.getElementById('add-shipping-service').addEventListener('click', function(e) {
        e.preventDefault();

        servicesElement.appendChild(getShippingService());
    });

    function getShippingGroupData() {
        var shippingCostElement = document.getElementsByClassName('shipping_cost_default')[0];
        var shippingGroupData = {
            services: [],
            shipping_rates: [],
            shipping_cost_default: shippingCostElement.value,
        };
        var services = document.getElementsByClassName('shipping-service');
        for (var i = 0, iLength = services.length; i < iLength; i++) {
            var service = services[i];
            var serviceId = service.getAttribute('id');
            shippingGroupData.services.push({
                'service_id': serviceId,
                'service_name': service.getElementsByClassName('service_name')[0].value,
                'service_code': service.getElementsByClassName('service_code')[0].value,
            });

            var rules = service.getElementsByClassName('shipping-rule');
            for (var j = 0, jLength = rules.length; j < jLength; j++) {
                var rule = rules[j];
                shippingGroupData.shipping_rates.push({
                    'service_id': serviceId,
                    'weight_from': parseFloat(rule.getElementsByClassName('weight_from')[0].value),
                    'weight_to': parseFloat(rule.getElementsByClassName('weight_to')[0].value),
                    'shipping_cost': parseFloat(rule.getElementsByClassName('shipping_cost')[0].value),
                });
            }
        }
        return shippingGroupData;
    }

    document.getElementById('shippinggroup_form').addEventListener('submit', function(e) {
        if (loadedShipping) {
            var data = JSON.stringify(getShippingGroupData());
            document.querySelector('#shipping-services-field [type="hidden"]').value = data;
        }
    });
});
