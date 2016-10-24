$(function() {
    var elems = Array.prototype.slice.call(document.querySelectorAll('.js-switch'));
    elems.forEach(function(html) {
        var switchery = new Switchery(html, {
            color: '#1AB394',
            size: 'small'
        });
    });
});
