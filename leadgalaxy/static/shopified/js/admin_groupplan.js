$(function(){
    django.jQuery('#id_parent_plan').change(function(){
        // Update permissions visisbility based on parent plan selection
        update_permissions_section();
    });
    // Don't need initial call, as django admin already does that for dropdown
    // update_permissions_section();

    function update_permissions_section(){
        var parent_selected=django.jQuery('#id_parent_plan').val();

        if (parent_selected!='') {
            django.jQuery('#id_permissions,#add_id_permissions').hide();
            django.jQuery('.parent_hint').remove();
            django.jQuery('#id_permissions').parent().append("<ul class='parent_hint' style='color: #b5b5b5;'><li>Using permissions from parent plan</li></ul>");
        }
        else {
            django.jQuery('#id_permissions,#add_id_permissions').show();
            django.jQuery('.parent_hint').remove();
        }

    }
});


