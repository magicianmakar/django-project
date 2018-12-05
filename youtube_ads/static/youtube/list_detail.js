(function() {
    'use strict';

    var writeUrls = function() {
        var videoUrls = [];
        var $links = $('.yt-video');

        for (var i = 0; i < $links.length; i++) {
            var link = $links[i];
            videoUrls.push(link.href);
        }

        $('#video-urls-textarea').text(videoUrls.join('\n'));
    };

    $('.delete-selected').on('click', function(e) {
        var listId = $('#video-list-table').data('video-list-id');
        var $checkboxes = $('table tbody input[type="checkbox"]');
        var videoIds = [];

        for (var i = 0; i < $checkboxes.length; i++) {
            var checkbox = $checkboxes[i];
            if (checkbox.checked) {
                videoIds.push(checkbox.id);
            }
        }

        $.ajax({
            type: 'DELETE',
            url: '/api/list-videos?' + $.param({ list_id: listId, video_ids: videoIds }),
            success: function(data) {
                if (data.status === 'ok') {
                    for (var i = 0; i < data.deleted.length; i++) {
                        $('#' + data.deleted[i]).parents('tr').remove();
                    }
                }
                writeUrls();
            }
        });
    });

    $('.del-video').click(function(e) {
        e.preventDefault();
        var params = {
            list_id: $(this).attr('list-id'),
            video_id: $(this).attr('video-id'),
        };
        $.ajax({
            type: 'DELETE',
            url: '/api/list-video?' + $.param(params),
            context: this,
            success: function(data) {
                if (data.status === 'ok') {
                    $(this).parents('tr').remove();
                    writeUrls();
                }
            },
            error: function(data) {
                displayAjaxError('Error', data);
            }
        });
    });

    $('.yt-video').click(function(e) {
        e.preventDefault();
        $.fancybox({
            'padding': 0,
            'autoScale': false,
            'transitionIn': 'none',
            'transitionOut': 'none',
            'title': this.title,
            'width': 640,
            'height': 385,
            'href': this.href.replace(new RegExp("watch\\?v=", "i"), 'v/'),
            'type': 'swf',
            'swf': {
                'wmode': 'transparent',
                'allowfullscreen': 'true'
            }
        });

        return false;
    });

    setTimeout(function() {
        $('#select-all').change(function() {
            var checked = this.checked;
            $('table input[type="checkbox"]').each(function(i, el) {
                el.checked = checked;
            });
        });
    }, 100);

    $("table").tablesorter();

    writeUrls();
})();
