var keyBenefitsIndex = 0;
document.addEventListener("DOMContentLoaded", function() {
    function addKeyBenefits(benefits) {
        var template = Handlebars.compile(document.getElementById('key-benefits-template').innerHTML);
        for (var i = 0, iLength = benefits.length; i < iLength; i++) {
            benefits[i].index = keyBenefitsIndex;
            keyBenefitsIndex += 1;
        }

        var wrapper = document.createElement('div');
        wrapper.innerHTML = template({'benefits': benefits});
        var keyBenefits = document.getElementById('key-benefits');
        while (wrapper.children.length > 0) {
            keyBenefits.appendChild(wrapper.children[0]);
        }

        keyBenefits.querySelectorAll('.close').forEach(function(item) {
            item.addEventListener('click', function(e) {
                e.preventDefault();
                var element = e.target;
                if (e.target.nodeName.toLowerCase() === 'span') {
                    element = element.parentNode;
                }
                element.parentNode.remove();
            });
        });
    }

    document.getElementById('add-key-benefit').addEventListener('click', function(e) {
        e.preventDefault();
        addKeyBenefits([{}]);
    });

    var existingBenefits = JSON.parse(document.getElementsByName('key_benefits')[0].value);
    addKeyBenefits(existingBenefits);
});
