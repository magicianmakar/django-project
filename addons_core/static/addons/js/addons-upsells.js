var selected_addons_upsells = Cookies.get('drop-addons-upsells');
if (selected_addons_upsells) {
    selected_addons_upsells = JSON.parse(decodeURIComponent(selected_addons_upsells));

    for (var addon in selected_addons_upsells) {
        $.ajax({
            url: api_url('install', 'addons'),
            type: 'post',
            data: {
                addon: selected_addons_upsells[addon]['id']
            }
        });
    }
    Cookies.remove('drop-addons-upsells');
}
