/* global $, store_id, store_type, templates_list, toastr, swal, displayAjaxError, api_url */

(function (store_id, store_type, templates_list) {
    'use strict';

    $('.edit-template').click(function (e) {
        e.preventDefault();
        var template_id = $(this).attr('data-template-id');

        var template = templates_list.find(function (item) {
            return String(item.id) === template_id;
        });

        if (template) {
            if (template.type === 'title_and_description') {
                setTitleTemplateData(template);
                $('#modal-title-template').modal('show');
            } else if (template.type === 'pricing') {
                setPricingTemplateData(template);
                $('#modal-price-template').modal('show');
            }
        }
    });

    $('.delete-template').click(function (e) {
        e.preventDefault();
        var template_id = $(this).attr('data-template-id');

        swal({
        title: "Delete Template",
        text: "Are you sure you want to delete this template?",
        type: "warning",
        showCancelButton: true,
        closeOnCancel: true,
        closeOnConfirm: false,
        confirmButtonColor: "#DD6B55",
        confirmButtonText: "Delete",
        cancelButtonText: "Cancel"
    },
    function(isConfirmed) {
        if (isConfirmed) {
            $.ajax({
                url: api_url('template', 'multichannel') + '?' + $.param({
                    template: template_id,
                }),
                type: 'DELETE',
                success: function (data) {
                    toastr.success('Template was successfully deleted!', 'Template Delete');
                    window.location.reload();
                },
                error: function (data) {
                    displayAjaxError('Template Delete', data);
                }
            });
        }
    });
    });

    // --- Title & Description template logic ---

    $('#add-title-template').click(function (e) {
        e.preventDefault();

        $('#modal-title-template input[name="title"]').val('{{ title }}');
        $('#modal-title-template textarea[name="description"]').val('{{ description }}');

        $('#modal-title-template').modal('show');
    });

    $('#modal-title-template').on('hide.bs.modal', function () {
        $('#modal-title-template input[name="name"]').val('');
        $('#modal-title-template input[name="title"]').val('');
        $('#modal-title-template textarea[name="description"]').val('');

        $('#modal-title-template .modal-title').text('Add New Title & Description Template');
        $('#modal-title-template .add-template-btn').removeClass('invisible');
        $('#modal-title-template .save-template-btn').addClass('invisible');
        $('#modal-title-template input[name=is_active]').prop('checked', false);
    });

    function setTitleTemplateData(template) {
        $('#modal-title-template .modal-title').text('Edit Title & Description Template');
        $('#modal-title-template .add-template-btn').addClass('invisible');
        $('#modal-title-template .save-template-btn').removeClass('invisible');

        $('#modal-title-template .save-template-btn').attr('data-template-id', template.id);

        if (template.is_active) {
            $('#modal-title-template input[name=is_active]').prop('checked', true);
        }

        $('#modal-title-template input[name="name"]').val(template.name);
        $('#modal-title-template input[name="title"]').val(template.title);
        $('#modal-title-template textarea[name="description"]').val(template.description);
    }

    $('#modal-title-template .add-template-btn').click(function (e) {
        if (!$('#modal-title-template input[name="name"]').val()) {
            $('#modal-title-template input[name="name"]').addClass('has-error');
            return;
        }

        var btn = $(this);

        var name = $('#modal-title-template input[name="name"]').val();
        var title = $('#modal-title-template input[name="title"]').val();
        var description = $('#modal-title-template textarea[name="description"]').val();
        var is_active = $('#modal-title-template input[name=is_active]').prop('checked');

        $.ajax({
            url: api_url('template-save', 'multichannel'),
            type: 'POST',
            data: JSON.stringify({
                'name': name,
                'type': 'title_and_description',
                'title': title,
                'description': description,
                'store_id': store_id,
                'store_type': store_type,
                'is_active': is_active,
            }),
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            context: {btn: btn},
            success: function (data) {
                if (data.status === 'ok') {
                    toastr.success('Template was successfully created!', 'Template Create');
                    $('#modal-title-template').modal('hide');
                    window.location.reload();
                } else {
                    displayAjaxError('Template Create', data);
                }
            },
            error: function (data) {
                displayAjaxError('Template Create', data);
            }
        });
    });

    $('#modal-title-template .save-template-btn').click(function (e) {
        if (!$('#modal-title-template input[name="name"]').val()) {
            $('#modal-title-template input[name="name"]').addClass('has-error');
            return;
        }

        var btn = $(this);

        var name = $('#modal-title-template input[name="name"]').val();
        var title = $('#modal-title-template input[name="title"]').val();
        var description = $('#modal-title-template textarea[name="description"]').val();
        var is_active = $('#modal-title-template input[name=is_active]').prop('checked');

        var template_id = $('#modal-title-template .save-template-btn').attr('data-template-id');

        $.ajax({
            url: api_url('template-save', 'multichannel'),
            type: 'POST',
            data: JSON.stringify({
                'name': name,
                'type': 'title_and_description',
                'title': title,
                'description': description,
                'store_id': store_id,
                'store_type': store_type,
                'template_id': template_id,
                'is_active': is_active,
            }),
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            context: {btn: btn},
            success: function (data) {
                if (data.status === 'ok') {
                    toastr.success('Template was successfully updated!', 'Template Update');
                    $('#modal-title-template').modal('hide');
                    window.location.reload();
                } else {
                    displayAjaxError('Template Update', data);
                }
            },
            error: function (data) {
                displayAjaxError('Template Update', data);
            }
        });
    });

    $('#modal-title-template input[name="name"]').change(function () {
        if ($('#modal-title-template input[name="name"]').hasClass('has-error')) {
            $('#modal-title-template input[name="name"]').removeClass('has-error');
        }
    });

    // --- Pricing template logic ---

    $('#add-pricing-template').click(function (e) {
        e.preventDefault();

        $('#price_amount').val(0.00);
        $('#price_override_amount').val(0.00);
        $('#compare_price_amount').val(0.00);
        $('#compare_price_override_amount').val(0.00);

        $('#modal-price-template').modal('show');
    });

    $('#modal-price-template input[type=radio][name="price_status"]').change(function () {
        if (this.value === 'inactive') {
            if ($('.price .calculated > label').hasClass('invisible')) {
                $('.price .calculated > label').removeClass('invisible');
            }
            if ($('.price .override > label').hasClass('invisible')) {
                $('.price .override > label').removeClass('invisible');
            }

            if (!$('.price .price-adjustment').hasClass('invisible')) {
                $('.price .price-adjustment').addClass('invisible');
            }
            if (!$('.price .price-override').hasClass('invisible')) {
                $('.price .price-override').addClass('invisible');
            }
        } else if (this.value === 'active_calculated') {
            if (!$('.price .calculated > label').hasClass('invisible')) {
                $('.price .calculated > label').addClass('invisible');
            }
            if ($('.price .override > label').hasClass('invisible')) {
                $('.price .override > label').removeClass('invisible');
            }

            if ($('.price .price-adjustment').hasClass('invisible')) {
                $('.price .price-adjustment').removeClass('invisible');
            }
            if (!$('.price .price-override').hasClass('invisible')) {
                $('.price .price-override').addClass('invisible');
            }
        } else if (this.value === 'active_override') {
            if ($('.price .calculated > label').hasClass('invisible')) {
                $('.price .calculated > label').removeClass('invisible');
            }
            if (!$('.price .override > label').hasClass('invisible')) {
                $('.price .override > label').addClass('invisible');
            }

            if (!$('.price .price-adjustment').hasClass('invisible')) {
                $('.price .price-adjustment').addClass('invisible');
            }
            if ($('.price .price-override').hasClass('invisible')) {
                $('.price .price-override').removeClass('invisible');
            }
        }
    });

    $('#modal-price-template input[type=radio][name="compare_price_status"]').change(function () {
        if (this.value === 'inactive') {
            if ($('.compare_price .calculated > label').hasClass('invisible')) {
                $('.compare_price .calculated > label').removeClass('invisible');
            }
            if ($('.compare_price .override > label').hasClass('invisible')) {
                $('.compare_price .override > label').removeClass('invisible');
            }

            if (!$('.compare_price .price-adjustment').hasClass('invisible')) {
                $('.compare_price .price-adjustment').addClass('invisible');
            }
            if (!$('.compare_price .price-override').hasClass('invisible')) {
                $('.compare_price .price-override').addClass('invisible');
            }
        } else if (this.value === 'active_calculated') {
            if (!$('.compare_price .calculated > label').hasClass('invisible')) {
                $('.compare_price .calculated > label').addClass('invisible');
            }
            if ($('.compare_price .override > label').hasClass('invisible')) {
                $('.compare_price .override > label').removeClass('invisible');
            }

            if ($('.compare_price .price-adjustment').hasClass('invisible')) {
                $('.compare_price .price-adjustment').removeClass('invisible');
            }
            if (!$('.compare_price .price-override').hasClass('invisible')) {
                $('.compare_price .price-override').addClass('invisible');
            }
        } else if (this.value === 'active_override') {
            if ($('.compare_price .calculated > label').hasClass('invisible')) {
                $('.compare_price .calculated > label').removeClass('invisible');
            }
            if (!$('.compare_price .override > label').hasClass('invisible')) {
                $('.compare_price .override > label').addClass('invisible');
            }

            if (!$('.compare_price .price-adjustment').hasClass('invisible')) {
                $('.compare_price .price-adjustment').addClass('invisible');
            }
            if ($('.compare_price .price-override').hasClass('invisible')) {
                $('.compare_price .price-override').removeClass('invisible');
            }
        }
    });

    $('#modal-price-template').on('hide.bs.modal', function () {
        $('#modal-price-template input[name="name"]').val('');

        $('.price #inactive').attr('checked', true).click().change();
        $('.compare_price #comp_inactive').attr('checked', true).click().change();

        $('#modal-price-template .modal-title').text('Add New Pricing Template');
        $('#modal-price-template .add-template-btn').removeClass('invisible');
        $('#modal-price-template .save-template-btn').addClass('invisible');

        $('#price_amount').val(0.00);
        $('#price_override_amount').val(0.00);

        $('#compare_price_amount').val(0.00);
        $('#compare_price_override_amount').val(0.00);
        $('#modal-price-template input[name=is_active]').prop('checked', false);
    });

    function validatePricing() {
        var hasErrors = false;

        var name = $('#modal-price-template input[name="name"]');
        if (!name.val()) {
            name.addClass('has-error');
            hasErrors = true;
        }

        var regExp = new RegExp('^[0-9]+(\\.[0-9]+)?$');

        var price_amount = $('#price_amount');
        if (!regExp.test(price_amount.val())) {
            price_amount.addClass('has-error');
            hasErrors = true;
        }

        var price_override_amount = $('#price_override_amount');
        if (!regExp.test(price_override_amount.val())) {
            price_override_amount.parent().addClass('has-error');
            hasErrors = true;
        }

        var compare_price_amount = $('#compare_price_amount');
        if (!regExp.test(compare_price_amount.val())) {
            compare_price_amount.addClass('has-error');
            hasErrors = true;
        }

        var compare_price_override_amount = $('#compare_price_override_amount');
        if (!regExp.test(compare_price_override_amount.val())) {
            compare_price_override_amount.parent().addClass('has-error');
            hasErrors = true;
        }

        return hasErrors;
    }

    function setPricingTemplateData(template) {
        $('#modal-price-template .modal-title').text('Edit Pricing Template');
        $('#modal-price-template .add-template-btn').addClass('invisible');
        $('#modal-price-template .save-template-btn').removeClass('invisible');

        $('#modal-price-template .save-template-btn').attr('data-template-id', template.id);

        $('#modal-price-template input[name="name"]').val(template.name);

        if (template.is_active) {
            $('#modal-price-template input[name=is_active]').prop('checked', true);
        }

        $('#price_direction').val(template.price_direction).change();
        $('#price_amount').val(template.price_amount);
        $('#price_modifier').val(template.price_modifier).change();
        $('#price_override_amount').val(template.price_override_amount);

        $('#compare_price_direction').val(template.compare_price_direction).change();
        $('#compare_price_amount').val(template.compare_price_amount);
        $('#compare_price_modifier').val(template.compare_price_modifier).change();
        $('#compare_price_override_amount').val(template.compare_price_override_amount);

        $('.price #' + template.price_status).attr('checked', true).click().change();
        $('.compare_price #comp_' + template.compare_price_status).attr('checked', true).click().change();
    }

    $('#modal-price-template .add-template-btn').click(function (e) {
        var hasErrors = validatePricing();
        if (hasErrors) {
            return;
        }

        var btn = $(this);

        var name = $('#modal-price-template input[name="name"]').val();

        var price_direction = $('#price_direction').val();
        var price_amount = $('#price_amount').val();
        var price_modifier = $('#price_modifier').val();
        var price_override_amount = $('#price_override_amount').val();

        var compare_price_direction = $('#compare_price_direction').val();
        var compare_price_amount = $('#compare_price_amount').val();
        var compare_price_modifier = $('#compare_price_modifier').val();
        var compare_price_override_amount = $('#compare_price_override_amount').val();

        var price_status = $('input[type=radio][name="price_status"]:checked').val();
        var compare_price_status = $('input[type=radio][name="compare_price_status"]:checked').val();

        var is_active = $('#modal-price-template input[name=is_active]').prop('checked');

        $.ajax({
            url: api_url('template-save', 'multichannel'),
            type: 'POST',
            data: JSON.stringify({
                'name': name,
                'type': 'pricing',
                'price_direction': price_direction,
                'price_amount': price_amount,
                'price_modifier': price_modifier,
                'price_override_amount': price_override_amount,
                'compare_price_direction': compare_price_direction,
                'compare_price_amount': compare_price_amount,
                'compare_price_modifier': compare_price_modifier,
                'compare_price_override_amount': compare_price_override_amount,
                'price_status': price_status,
                'compare_price_status': compare_price_status,
                'store_id': store_id,
                'store_type': store_type,
                'is_active': is_active,
            }),
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            context: {btn: btn},
            success: function (data) {
                if (data.status === 'ok') {
                    toastr.success('Template was successfully created!', 'Template Create');
                    $('#modal-title-template').modal('hide');
                    window.location.reload();
                } else {
                    displayAjaxError('Template Create', data);
                }
            },
            error: function (data) {
                displayAjaxError('Template Create', data);
            }
        });
    });

    $('#modal-price-template .save-template-btn').click(function (e) {
        var hasErrors = validatePricing();
        if (hasErrors) {
            return;
        }

        var btn = $(this);

        var name = $('#modal-price-template input[name="name"]').val();
        var price_direction = $('#price_direction').val();
        var price_amount = $('#price_amount').val();
        var price_modifier = $('#price_modifier').val();
        var price_override_amount = $('#price_override_amount').val();

        var compare_price_direction = $('#compare_price_direction').val();
        var compare_price_amount = $('#compare_price_amount').val();
        var compare_price_modifier = $('#compare_price_modifier').val();
        var compare_price_override_amount = $('#compare_price_override_amount').val();

        var price_status = $('input[type=radio][name="price_status"]:checked').val();
        var compare_price_status = $('input[type=radio][name="compare_price_status"]:checked').val();

        var is_active = $('#modal-price-template input[name=is_active]').prop('checked');

        var template_id = $('#modal-price-template .save-template-btn').attr('data-template-id');

        $.ajax({
            url: api_url('template-save', 'multichannel'),
            type: 'POST',
            data: JSON.stringify({
                'name': name,
                'type': 'pricing',
                'price_direction': price_direction,
                'price_amount': price_amount,
                'price_modifier': price_modifier,
                'price_override_amount': price_override_amount,
                'compare_price_direction': compare_price_direction,
                'compare_price_amount': compare_price_amount,
                'compare_price_modifier': compare_price_modifier,
                'compare_price_override_amount': compare_price_override_amount,
                'price_status': price_status,
                'compare_price_status': compare_price_status,
                'store_id': store_id,
                'store_type': store_type,
                'template_id': template_id,
                'is_active': is_active,
            }),
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            context: {btn: btn},
            success: function (data) {
                if (data.status === 'ok') {
                    toastr.success('Template was successfully updated!', 'Template Update');
                    $('#modal-title-template').modal('hide');
                    window.location.reload();
                } else {
                    displayAjaxError('Template Update', data);
                }
            },
            error: function (data) {
                displayAjaxError('Template Update', data);
            }
        });
    });

    $('#modal-price-template input[name="name"]').change(function () {
        if ($('#modal-price-template input[name="name"]').hasClass('has-error')) {
            $('#modal-price-template input[name="name"]').removeClass('has-error');
        }
    });

    $('#modal-price-template input[name="price_amount"]').change(function () {
        if ($('#modal-price-template input[name="price_amount"]').hasClass('has-error')) {
            $('#modal-price-template input[name="price_amount"]').removeClass('has-error');
        }
    });

    $('#modal-price-template input[name="price_override_amount"]').change(function () {
        if ($('#modal-price-template input[name="price_override_amount"]').hasClass('has-error')) {
            $('#modal-price-template input[name="price_override_amount"]').removeClass('has-error');
        }
    });

    $('#modal-price-template input[name="compare_price_amount"]').change(function () {
        if ($('#modal-price-template input[name="compare_price_amount"]').hasClass('has-error')) {
            $('#modal-price-template input[name="compare_price_amount"]').removeClass('has-error');
        }
    });

    $('#modal-price-template input[name="compare_price_override_amount"]').change(function () {
        if ($('#modal-price-template input[name="compare_price_override_amount"]').hasClass('has-error')) {
            $('#modal-price-template input[name="compare_price_override_amount"]').removeClass('has-error');
        }
    });

})(store_id, store_type, templates_list);