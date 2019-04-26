$(document).ready(function() {
    'use strict';

    var $trialDaysLeft = $('#trial_days_left');

    $trialDaysLeft.find('button').click(function() { $trialDaysLeft.hide(); });

    var $isExtensionReady = isExtensionReady();

    $isExtensionReady.done(function() {
        $.post(api_url('extension-is-installed', 'goals')).done(function(data) {
            if (data.added) {
                incrementTotalStepsCompleted();
                markStepCircleAsCompleted(data.slug);
            }
        });
    });

    function incrementTotalStepsCompleted() {
        var $totalStepsCompleted = $('.total-steps-completed');
        var total = parseInt($totalStepsCompleted.html());
        $totalStepsCompleted.html(++total);
    }

    function markStepCircleAsCompleted(slug) {
        $('.' + slug + '-circle').removeClass('disabled-gray').addClass('dropified-green');
    }
});
