(function() {
    'use strict';

    $("table").tablesorter();

    setTimeout(function () {
        $('#select-all').change(function(){
            var checked = this.checked;
            $('table input[type="checkbox"]').each(function(i, el) {
                el.checked=checked;
            });
        });
    }, 100);
})();
