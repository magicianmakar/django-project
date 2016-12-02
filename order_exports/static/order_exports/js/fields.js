window.OrderExportAdd = {
    fieldsSelect: $('.chosen-select'),
    selectableFields: $('.selectable'),
    fieldsList: $('.nestable'),
    init: function() {
        this.initializeFieldsSelect();
        this.initializeFieldsList();

        // events
        this.onClickEdit();
        this.onUnselectField();
        this.onToggleUsername();
        var clockpickerInput = $('input[name="schedule"]');
        clockpickerInput.clockpicker({
            autoclose: true,
            afterHourSelect: function(e) {
                clockpickerInput.clockpicker('done');
            }
        });

        $('input[name="daterange"]').daterangepicker();
    },
    onClickEdit: function() {
        $('.field-wrapper').hide();
        $('.edit').on('click', function(e) {
            e.preventDefault();
            $(this).parents('.nestable').siblings('.field-wrapper').show();
            $(this).hide();
        });
    },
    initializeFieldsSelect: function() {
        var OrderExportAdd = this;
        $('input[name="previous_day"]').on('ifChecked', function() {
            $('#schedule .range').hide();
            $('#schedule .daily').show();
            $('input[name="receiver"]').parents('.form-group').show();
            $('#vendor-login').show();
        });

        $('input[name="previous_day"]').on('ifUnchecked', function() {
            $('#schedule .range').show();
            $('#schedule .daily').hide();
            $('input[name="receiver"]').val('').parents('.form-group').hide();
            $('#vendor-login').hide();
        });

        this.selectableFields.on("ifChecked", function() {
            var self = this;
            $(this).parents('.icheck').fadeOut(200, function() {
                var wrapper = $(self).parents('.field-wrapper'),
                    list = wrapper.siblings('.nestable').find('.dd-list');

                list.find('a.edit').before(
                    $('<li data-id="'+$(self).attr('name')+'" class="dd-item">').append(
                        $('<div class="dd-handle">').append($(self).parents('.icheck'))
                    )
                );
                $(self).parents('.icheck').fadeIn(200);

                data = list.find('li').map(function(key, value) {
                    return $(value).attr('data-id');
                }).get();
                
                wrapper.siblings('.output').val(window.JSON.stringify(data));
            });

        }).on('ifUnchecked', function() {
            var ddItem = $(this).parents('.dd-item');
            $('.field-wrapper[data-name="'+$(this).attr('name')+'"]').html($(this).parents('.icheck'));
            ddItem.remove();

            var wrapper = $(this).parents('.field-wrapper'),
                list = wrapper.siblings('.nestable').find('.dd-list');

            data = list.find('li').map(function(key, value) {
                return $(value).attr('data-id');
            }).get();
            
            wrapper.siblings('.output').val(window.JSON.stringify(data));
        });
    },
    initializeFieldsList: function() {
        var OrderExportAdd = this;

        this.fieldsList.nestable({
            maxDepth: 1
        }).on('change', function (e) {
            var list = e.length ? e : $(e.target),
                output = list.data('output'),
                data = list.nestable('serialize');

            data = $(this).find('li').map(function(key, value) {
                return $(value).attr('data-id');
            }).get();
            
            output.val(window.JSON.stringify(data));
        });

        var updateOutput = function (e) {
            var list = e.length ? e : $(e.target),
                output = list.data('output');

            data = list.find('li').map(function(key, value) {
                return $(value).attr('data-id');
            }).get();
            
            output.val(window.JSON.stringify(data));
        };

        this.fieldsList.each(function() {
            updateOutput($(this).data('output', $(this).next('[type="hidden"]')));
        });
    },
    updateFields: function(select) {
        var data = select.next().find('.search-choice').map(function(key, value) {
            var index = parseInt($(this).find('.search-choice-close').attr('data-option-array-index'));

            return select.find('option:nth-child('+(index+1)+')').val();
        });

        OrderExportAdd.updateList(select.parents('.form-group').next().find('.nestable'), data);
    },
    onUnselectField: function() {
        $('.unselect').on('mousedown', function(e) {
            e.preventDefault();
            e.stopPropagation();

            var formGroup = $(this).parents('div.nestable').parents('.form-group').prev('.form-group'),
                selectValue = $(this).parents('li.dd-item').attr('data-id'),
                fieldIndex = formGroup.find('option[value="'+selectValue+'"]').index();

            formGroup.find('.search-choice-close[data-option-array-index="'+fieldIndex+'"]').trigger('click');
        }).on('click', function(e) {
            e.preventDefault();
        });
    },
    orderSelect: function(list, select) {
        var choices = select.next().find('.chosen-choices');
        for (var i = 0, iLength = list.length; i < iLength; i++) {
            var item = list[i].id,
                itemText = select.find('option[value="'+item+'"]').text(),
                found = choices.find('.search-choice').filter(function() {
                    return $(this).text().trim() == itemText;
                });
            choices.append(found);
        }
        choices.append(choices.find('.search-field'));
    },
    createListItem: function(list, id) {
        var text = list.parents('.form-group').prev('.form-group').find(
            'select option[value="'+id+'"]').text().trim();
        return $('<li class="dd-item" data-id="'+id+'">').append(
            $('<div class="dd-handle">').append(
                text, 
                $('<a href="#" class="unselect close">').append(
                    $('<i class="fa fa-times">')
                )
            )
        );
    },
    updateList: function(list, data) {
        list = list.find('.dd-list');
        list.children().remove();

        for (var i = 0, iLength = data.length; i < iLength; i++) {
            var item = data[i],
                listItem = list.find('li:nth-child('+i+')');

            if (listItem.length == 0) {
                list.append(this.createListItem(list, item));
            } else if (listItem.attr('data-id') != item) {
                listItem.after(this.createListItem(list, item));
            }
        }
    },
    onToggleUsername: function() {
        $('[name="vendor_user"]').on('change', function() {
            if ($(this).val() != '') {
                $('[name="vendor_username"]').val('');
                $('[name="vendor_email"]').val('');
            }
        });
        
        $('[name="vendor_username"]').on('keyup', function() {
            if ($(this).val() != '') {
                $('[name="vendor_user"]').val('');
            }
        });

        $('[name="vendor_email"]').on('keyup', function() {
            if ($(this).val() != '') {
                $('[name="vendor_user"]').val('');
            }
        });
    }
};

window.OrderExportAdd.init();
