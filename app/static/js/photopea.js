var PhotoPeaEditor = {
    currentAction: '',
    dataObj: null,
    queue: [],
    phase: 1,
    deferred: $.Deferred(),
    running: false,
    photoPeaWindow: $('#photopea').get(0).contentWindow,
    init: function() {
        this.doInit();
        this.listenIncomingAction();
    },
    listenIncomingAction: function() {
        window.addEventListener("message", function(e) {
            if (e.origin.indexOf('photopea') > -1) {
                if (typeof e.data !== 'object' && e.data.indexOf('save:') == 0) {
                    PhotoPeaEditor.doSave(e.data.replace('save:', ''));
                }
            }
        });
    },
    listenSentAction: function(e) {
        if (e.origin.indexOf('photopea') > -1) {
            if (PhotoPeaEditor.phase <= 2 && e.data === 'done') {
                window.removeEventListener("message", PhotoPeaEditor.listenSentAction);

                var eventData = e.target.actionData;
                switch (PhotoPeaEditor.currentAction) {
                    case 'init':
                        PhotoPeaEditor.onInit(eventData);
                        PhotoPeaEditor.deferred.resolve();
                    break;
                    case 'save':
                        eventData['arrayBuffer'] = PhotoPeaEditor.dataObj;
                        PhotoPeaEditor.onSave(eventData);
                        PhotoPeaEditor.deferred.resolve();
                    break;
                    case 'load':
                        PhotoPeaEditor.onLoad(eventData);
                        PhotoPeaEditor.deferred.resolve();
                    break;
                    default:
                        PhotoPeaEditor.deferred.reject();
                    break;
                }
                PhotoPeaEditor.actionDone();
            } else if (typeof e.data === 'object') {
                PhotoPeaEditor.dataObj = e.data;
            } else if (PhotoPeaEditor.phase > 2) {
                PhotoPeaEditor.deferred.reject();
            } else {
                PhotoPeaEditor.phase += 1;
            }
        }
    },
    actionDone: function() {
        PhotoPeaEditor.currentAction = '';
        PhotoPeaEditor.phase = 1;
    },
    actionAdd: function(action) {
        PhotoPeaEditor.queue.push(function() {
            var actionData = action();
            window.addEventListener("message", PhotoPeaEditor.listenSentAction);
            window.actionData = actionData;
            return PhotoPeaEditor.deferred.promise();
        });
        PhotoPeaEditor.actionStartRun();
    },
    actionStartRun: function() {
        if (!PhotoPeaEditor.running) {
            PhotoPeaEditor.actionRun();
        }
    },
    actionRun: function() {
        var nextAction = PhotoPeaEditor.queue.shift();
        if (nextAction) {
            PhotoPeaEditor.running = true;
            nextAction().done(function() {
                setTimeout(function() {
                    PhotoPeaEditor.actionRun();
                }, 1000);  // Wait before moving to next action
            }).fail(function() {
                console.error('error getting response from photopea');
            });
        } else {
            PhotoPeaEditor.running = false;
        }
    },
    doInit: function() {
        PhotoPeaEditor.actionAdd(function() {
            PhotoPeaEditor.currentAction = 'init';
            var photoPeaConfig = encodeURI(JSON.stringify({
                "environment": {
                    "customIO"  : {
                        "save": "app.echoToOE('save:' + app.activeDocument.source);"
                    },
                    "localsave": true
                }
            }));
            $('#modal-photopea iframe').attr('src', 'https://www.photopea.com?p=' + photoPeaConfig);

            return {};
        });
    },
    doLoad: function(imageUrl, imageId) {
        PhotoPeaEditor.actionAdd(function() {
            PhotoPeaEditor.currentAction = 'load';

            $('#modal-photopea').modal('show');
            setTimeout(function() {
                var wnd = document.getElementById("photopea").contentWindow;

                fetch(imageUrl, {cache: "no-cache"}).then(function(response) {
                    return response.arrayBuffer();
                }).then(function(arrayBuffer) {
                    wnd.postMessage(arrayBuffer, "*");
                }).catch(function(err) {
                    console.error('error loading image', err);
                });
            }, 1000);

            return {'url': imageUrl, 'id': imageId};
        });
    },
    doSave: function(sourceId) {
        PhotoPeaEditor.actionAdd(function() {
            PhotoPeaEditor.currentAction = 'save';
            PhotoPeaEditor.postMessage("app.activeDocument.saveToOE('png');");

            return {'sourceId': sourceId};
        });
    },
    onInit: function(data) {
        PhotoPeaEditor.postMessage("app.echoToOE('init done');");
    },
    onSave: function(data) {
        var imageID = data.sourceId;
        var img = document.getElementById(imageID);

        if (img) {
            var oldURL = img.src;

            var blob = new Blob([data.arrayBuffer], {type: "image/png"});
            var reader = new FileReader();
            reader.onload = function(e) {
                img.src = e.target.result;
            };
            reader.readAsDataURL(blob);

            var formData = new FormData();
            formData.append("image", blob, imageID + '.png');
            formData.append('product', config.product_id);
            formData.append('old_url', document.getElementById(data.sourceId).src);
            formData.append('advanced', true);

            $.ajax({
                url: '/upload/save_image_s3',
                type: 'POST',
                data: formData,
                contentType: false,
                processData: false,
                context: {'img': img, 'imageID': imageID},
                success: function (data) {
                    if (data.status == 'ok') {
                        this.img.src = data.url;
                        product.images[parseInt($('#'+this.imageID).attr('image-id'))] = data.url;
                        PhotoPeaEditor.postMessage("app.activeDocument.close();");
                        $('#modal-photopea').modal('hide');
                    } else {
                        displayAjaxError('PhotoPea Image Editor', data);
                    }
                },
                error: function(data) {
                    displayAjaxError('PhotoPea Image Editor', data);
                }
            });
        } else {
            PhotoPeaEditor.postMessage("app.activeDocument.close();");
            $('#modal-photopea').modal('hide');
        }
    },
    onLoad: function(data) {
        PhotoPeaEditor.postMessage("app.activeDocument.source='" + data.id + "';");
        PhotoPeaEditor.postMessage("app.activeDocument.name='" + data.id + "';");
    },
    postMessage: function(script) {
        document.getElementById("photopea").contentWindow.postMessage(script, "*");
    }
};
PhotoPeaEditor.init();
