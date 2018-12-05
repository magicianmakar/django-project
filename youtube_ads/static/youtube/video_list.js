(function() {
    'use strict';

    $("#copy-selected").on('click', function() {
        var text = '';
        $('table tbody input[type="checkbox"]').each(function(i, el) {
            if (el.checked) {
                text += 'https://www.youtube.com/watch?v=' + $(el).attr('id') + '\n';
            }
        });

        if (text.length == 0) {
            alert('Select a video first');
        } else {
            $('#copy-videos').val(text);
            $('#copy-videos').select();
            document.execCommand("copy");
        }
    });

    $("table").tablesorter();

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

    $('.save-to-list').click(function() {
        var selected = [];
        $('table tbody input[type="checkbox"]').each(function(i, el) {
            if (el.checked) {
                selected.push($(el).attr('id'));
            }
        });

        $.ajax({
            type: 'GET',
            url: '/api/video-lists',
            dataType: 'json',
            success: function(data) {
                $('select#user-list').html($('<option>', {}));
                var lists = data.lists;
                for (var i = 0; i < lists.length; i++) {
                    $('select#user-list').append($('<option>', { value: lists[i].id, text: lists[i].title }));
                }

                $('#myModal').modal('show');
            }
        });

    });

    $('button#save-list').click(function() {
        var selected = '';
        $('table tbody input[type="checkbox"]').each(function(i, el) {
            if (el.checked) {
                selected += $(el).attr('id') + ';';
            }
        });

        var newListTitle = $('#new-list').val();
        var selectedList = $('#user-list').val();

        var data = {
            selected: selected,
            newListTitle: newListTitle,
            selectedList: selectedList
        };

        $.ajax({
            type: 'POST',
            url: '/api/video-list',
            data: data,
            success: function(data) {
                if (data.status === 'ok') {
                    $('#new-list').val('');
                    $('#myModal').modal('hide');
                    window.location.pathname = '/tubehunt/lists/' + data.id;
                }
            },
            error: function(data) {
                displayAjaxError('Error', data);
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
                }
            },
            error: function(data) {
                displayAjaxError('Error', data);
            }
        });
    });

    setTimeout(function() {
        $('#select-all').change(function() {
            var checked = this.checked;
            $('table input[type="checkbox"]').each(function(i, el) {
                el.checked = checked;
            });
        });
    }, 100);
})();
