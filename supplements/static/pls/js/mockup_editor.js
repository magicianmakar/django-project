var MockupEditor = (function() {
    return {
        mockups: [],
        labelMockups: JSON.parse($('[name="label_presets"]').val()),
        image: null,
        mockupLayers: mockupLayers,
        totalImages: mockupLayers.length,
        loadedImages: 0,
        canvasSize: 400,
        saveCanvasSize: null,
        labelScale: 6,
        currentZoom: 100,
        maxZoom: 150,
        minZoom: 50,
        useControls: window.location.href.indexOf('debug=1') > -1,
        control: 'label',  // label or mockup
        controlIndex: null,
        wrapLabel: function(canvas) {
            // http://plnkr.co/edit/83xAr99FjswWg0GHjDvJ?p=preview&preview
            var ctx = canvas.getContext('2d');
            function start() {
                var iw = this.width;
                var ih = this.height;

                var xOffset = 100,
                    yOffset = 200;

                var a = 400;
                var b = 400;

                var scaleFactor = iw / (2*a); //how many times original image is greater compared to our rendering area?

                // draw vertical slices
                for (var X = 0; X < iw; X+=1) {
                  var y = b/a * Math.sqrt(a*a - (X-a)*(X-a)); // ellipsis equation
                  ctx.drawImage(this, X * scaleFactor, 0, 6, ih, X + xOffset, y + yOffset, 1, ih - 605 + y/2);
                }
            }

            var img = new Image();
            img.onload = start;
            img.src = canvas.toDataURL();
        },
        dataURLtoFile: function(dataurl, filename) {
            var arr = dataurl.split(','), mime = arr[0].match(/:(.*?);/)[1],
                bstr = atob(arr[1]), n = bstr.length, u8arr = new Uint8Array(n);
            while(n--){
                u8arr[n] = bstr.charCodeAt(n);
            }
            return new File([u8arr], filename, {type:mime});
        },
        setLabel: function(fileData) {
            MockupEditor.mockupLayers.forEach(function(layer) {
                if (layer.layer === 'label') {
                    if (MockupEditor.loadedImages === MockupEditor.totalImages) {
                        MockupEditor.loadedImages -= 1;
                    }
                    layer.image = null;
                    layer.file = fileData;

                    MockupEditor.loadImages(function() {
                        MockupEditor.labelMockups.forEach(function(dimension, i) {
                            MockupEditor.setDimensions(dimension);
                            MockupEditor.save(i);
                            $('#modal-mockup-images .modal-content').removeClass('loading');
                        });
                    });
                }
            });
            $('#mockup-editor').removeClass('hidden');
        },
        setDimensions: function(dimensions) {
            // :dimensions: [{left:0,top:0,size:1,bgLeft:0,bgTop:0,bgSize:1}]
            $('#mockup-editor .btn-group').addClass('hidden');
            $('#mockup-editor .btn-index').empty();
            MockupEditor.controlIndex = null;
            if (MockupEditor.useControls && !$('#save-mockup').hasClass('hidden')) {
                $('#mockup-editor .btn-group').removeClass('hidden');
            }
            var dimensionsLength = dimensions.length;
            MockupEditor.mockups = dimensions.map(function(preset, i) {
                if (dimensionsLength > 1) {
                    $('#mockup-editor .btn-index').append(
                        $('<button type="button" class="btn btn-success">').text(preset.name || (i + 1))
                    );
                }

                return $.extend({left: 0, top: 0, size: 1}, preset, {
                    bgLeft: preset.bgLeft || 0,
                    bgTop: preset.bgTop || 0,
                    bgSize: preset.bgSize || 1,
                    canvas: $('<canvas class="mockup-canvas" height="'+MockupEditor.canvasSize+'" width="'+MockupEditor.canvasSize+'">').get(0),
                    bgCanvas: $('<canvas class="mockup-canvas" height="'+MockupEditor.canvasSize+'" width="'+MockupEditor.canvasSize+'">').get(0),
                });
            });
        },
        getDimensions: function() {
            $('#mockup-editor .btn-group').addClass('hidden');
            var dimensions = MockupEditor.mockups.map(function(mockup) {
                var mockupClone = $.extend({}, mockup);
                delete mockupClone.canvas;
                delete mockupClone.bgCanvas;
                return mockupClone;
            });

            return dimensions;
        },
        combineLayers: function() {
            var layers = MockupEditor.mockupLayers;
            layers.forEach(function(layer) {
                if (!layer.combined) {
                    return;
                }
                MockupEditor.loadedImages -= 1;
                var combined = layers.filter(function(l) {
                    return layer.combined.indexOf(l.layer) > -1;
                });
                if (layer.unmasked) {
                    combined.push($.extend({}, layer));
                } else {
                    // Using previous layers to mask last one
                    combined.push($.extend({}, layer, {'mode': 'source-in'}));
                }

                var canvas = $('<canvas width="' + layer.image.width + '" height="' + layer.image.height + '">').get(0);
                var context = canvas.getContext('2d');
                combined.forEach(function(l) {
                    context.globalCompositeOperation = l.mode || 'source-over';
                    context.drawImage(l.image, 0, 0);
                });
                layer.image.src = canvas.toDataURL();
                layer.combined = false;
            });
        },
        loadImages: function(callback) {
            callback = typeof(callback) !== 'undefined' ? callback : function() {};
            var imageLoaded = function() {
                MockupEditor.loadedImages += 1;
                if (MockupEditor.loadedImages === MockupEditor.totalImages) {
                    // Merge layers and reload
                    MockupEditor.combineLayers();
                    if (MockupEditor.loadedImages === MockupEditor.totalImages) {
                        callback();
                    }
                }
            };
            MockupEditor.mockupLayers.forEach(function(layer) {
                if (!layer.file) {
                    MockupEditor.loadedImages += 1;
                    return;
                }
                if (layer.image) {
                    return;
                }
                var img = new Image();
                img.src = layer.file;
                img.onload = imageLoaded;
                layer.image = img;
                if (layer.layer === 'label') {
                    MockupEditor.saveCanvasSize = layer.saveSize;
                    MockupEditor.image = img;
                }
            });
        },
        resizeMockup: function(mockup, points) {
            if (MockupEditor.control === 'label') {
                mockup.size = mockup.size * points / MockupEditor.currentZoom;
            } else {
                mockup.bgSize = mockup.bgSize * points / MockupEditor.currentZoom;
            }
        },
        resize: function(points) {
            if (MockupEditor.minZoom <= points && points < MockupEditor.maxZoom) {
                if (MockupEditor.controlIndex !== null) {
                    var mockup = MockupEditor.mockups[MockupEditor.controlIndex];
                    MockupEditor.resizeMockup(mockup, points);
                } else {
                    MockupEditor.mockups.forEach(function(mockup) {
                        MockupEditor.resizeMockup(mockup, points);
                    });
                }

                MockupEditor.currentZoom = points;
                MockupEditor.generate();
            }
        },
        moveMockup: function(mockup, top, left) {
            // TODO: add more exact calculation for percentage positioning
            if (MockupEditor.control === 'label') {
                mockup.left += left / (MockupEditor.image.width / mockup.size) * MockupEditor.labelScale;
                mockup.top += top / (MockupEditor.image.height / mockup.size) * MockupEditor.labelScale;
            } else {
                mockup.bgLeft -= left / MockupEditor.canvasSize;
                mockup.bgTop -= top / MockupEditor.canvasSize;
            }
        },
        move: function(top, left) {
            if (MockupEditor.controlIndex !== null) {
                var mockup = MockupEditor.mockups[MockupEditor.controlIndex];
                MockupEditor.moveMockup(mockup, top, left);
            } else {
                MockupEditor.mockups.forEach(function(mockup) {
                    MockupEditor.moveMockup(mockup, top, left);
                });
            }

            MockupEditor.generate();
        },
        loadEvents: function(currentCanvas) {
            var labelMoving;
            var labelOffsetX;
            var labelOffsetY;
            currentCanvas.onmousedown = function(e) {
                labelMoving = true;
                labelOffsetX = e.clientX;
                labelOffsetY = e.clientY;
                currentCanvas.style.cursor = 'grabbing';
            };
            currentCanvas.onmouseup = function(e){
                labelMoving = false;
                currentCanvas.style.cursor = 'grab';
            };
            currentCanvas.onmousemove = function(e){
                if (labelMoving) {
                    var left = labelOffsetX - e.clientX;
                    var top = labelOffsetY - e.clientY;

                    MockupEditor.move(top, left);
                    labelOffsetX = e.clientX;
                    labelOffsetY = e.clientY;
                }
            };
            currentCanvas.onwheel = function(e) {
                e.preventDefault();
                var points = MockupEditor.currentZoom + (e.wheelDelta / MockupEditor.maxZoom);
                MockupEditor.resize(points);

                // Doesn't call slide event
                $('#mockup-editor .zoom-slider').slider('value', MockupEditor.currentZoom);
            };

            $("#mockup-editor .zoom-slider").slider();
            $("#mockup-editor .zoom-slider").slider('destroy');
            $("#mockup-editor .zoom-slider").slider({
                orientation: 'vertical',
                value: MockupEditor.currentZoom,
                min: MockupEditor.minZoom,
                max: MockupEditor.maxZoom,
                step: 0.1,
                slide: function (e, ui) {
                    MockupEditor.resize(ui.value);
                }
            });
        },
        loadCanvas: function() {
            var lastCanvas = null;
            MockupEditor.unloadCanvas();
            MockupEditor.mockups.forEach(function(mockup) {
                $('#mockup-editor .canvas-group').append(mockup.bgCanvas, mockup.canvas);
                lastCanvas = mockup.canvas;
            });
            if (lastCanvas) {
                MockupEditor.loadEvents(lastCanvas);
            }
        },
        unloadCanvas: function() {
            $('#mockup-editor .canvas-group canvas').remove();
        },
        generate: function(mockups) {
            var curveCanvas;
            generateMockups = typeof(mockups) !== 'undefined' ? mockups : MockupEditor.mockups;
            generateMockups.forEach(function(mockup) {
                var context = mockup.canvas.getContext('2d');
                var bgContext = mockup.bgCanvas.getContext('2d');
                var currentContext;

                context.clearRect(0, 0, mockup.canvas.width, mockup.canvas.height);
                bgContext.clearRect(0, 0, mockup.canvas.width, mockup.canvas.height);
                mockupLayers.forEach(function(layer) {
                    if (!layer.image || !layer.mode) {
                        return;
                    }
                    if (mockup.layers && mockup.layers[layer.layer] === false) {
                        return;
                    }

                    var positionLeft = mockup.canvas.width * mockup.bgLeft;
                    var positionTop = mockup.canvas.height * mockup.bgTop;
                    var positionRight = mockup.canvas.width * mockup.bgSize;
                    var positionBottom = mockup.canvas.height * mockup.bgSize;

                    // Respect square size of canvas
                    var layerWidth = layer.image.width;
                    var layerHeight = layer.image.width;
                    var layerLeft = 0;
                    var layerTop = 0;

                    if (layer.position) {
                        positionLeft += positionRight * layer.position.left;
                        positionTop += positionBottom * layer.position.top;
                        positionRight *= layer.position.right;
                        positionBottom *= layer.position.bottom;

                        layerWidth *= layer.position.right;
                        layerHeight *= layer.position.bottom;
                        layerLeft = layer.image.width * layer.position.left;
                        layerTop = layer.image.height * layer.position.top;
                    }

                    if (layer.layer === 'label') {
                        layerWidth *= mockup.size;
                        layerHeight *= mockup.size;
                        layerLeft = layer.image.width * mockup.left;
                        layerTop = layer.image.height * mockup.top;
                    }

                    currentContext = layer.background ? bgContext : context;
                    currentContext.globalCompositeOperation = layer.mode;
                    currentContext.drawImage(
                        layer.image,
                        layerLeft, layerTop,  // Start clipping
                        layerWidth, layerHeight,  // End clipping
                        positionLeft, positionTop,  // Fixed position
                        positionRight, positionBottom // Fixed size
                    );
                });
            });
        },
        save: function(index) {
            // Draw on bigger canvas instead of resizing drawn canvases
            var canvas = $('<canvas>');
            canvas.attr('width', MockupEditor.saveCanvasSize);
            canvas.attr('height', MockupEditor.saveCanvasSize);

            var resizedMockups = MockupEditor.mockups.map(function(mockup) {
                return $.extend({}, mockup, {
                    canvas: canvas.clone().get(0),
                    bgCanvas: canvas.clone().get(0),
                });
            });
            MockupEditor.generate(resizedMockups);

            canvas = canvas.get(0);
            var context = canvas.getContext('2d');
            resizedMockups.forEach(function(mockup) {
                context.drawImage(mockup.bgCanvas, 0, 0);
                context.drawImage(mockup.canvas, 0, 0);
                mockup.canvas.remove();
                mockup.bgCanvas.remove();
            });
            $('.previews .mockup-item:nth-child(' + (index + 1) + ') img').attr('src', canvas.toDataURL());
            canvas.remove();

            MockupEditor.labelMockups[index] = MockupEditor.getDimensions();
            MockupEditor.unloadCanvas();
            MockupEditor.currentZoom = 100;
        }
    };
}());

function addLabelImage(pdf) {
    $('#modal-mockup-images .modal-content').addClass('loading');
    pdfjsLib.getDocument(pdf).promise.then(function(pdf) {
        pdf.getPage(1).then(function(page) {
            var viewport = page.getViewport({scale: MockupEditor.labelScale});

            var canvas = $('<canvas>').get(0);
            canvas.width = viewport.width;
            canvas.height = viewport.height;
            var context = canvas.getContext('2d');

            page.render({
                canvasContext: context,
                viewport: viewport
            }).promise.then(function() {
                MockupEditor.setLabel(canvas.toDataURL());
                $('#save-mockups').prop('disabled', false);
            });
        });
    });
}

function labelSizeMatch(defaultSize, pdf) {
    var defaultWidth = defaultSize.split('x')[0];
    var defaultHeight = defaultSize.split('x')[1];
    return new Promise(function (resolve, reject) {
        if (window.location.href.indexOf('debug=1') > -1) {
            resolve();
        }
        pdfjsLib.getDocument(pdf).promise.then(function(pdf) {
            pdf.getPage(1).then(function(page) {
                var pdfWidth = (page._pageInfo.view[2] / 72).toFixed(3); // returned in pt => pt / 72 = 1 in
                var pdfHeight = (page._pageInfo.view[3] / 72).toFixed(3);

                /*
                Label size can have a margin of +0.125 (in inches).
                PLS approve and can print labels which are label size or label size + 0.125 margin. Sizes in between or any other variations  are not allowed.
                */
                var margin = 0.125;
                var defaultHeightWithMargin = parseFloat(defaultHeight) + margin;
                var defaultWidthWithMargin = parseFloat(defaultWidth) + margin;

                if ((pdfHeight === defaultHeight && pdfWidth === defaultWidth) || (parseFloat(pdfHeight) === defaultHeightWithMargin && parseFloat(pdfWidth) === defaultWidthWithMargin)) {
                    resolve();
                } else {
                    reject();
                }
            });
        });
    });
}

$('#label').on('change', function() {
    var reader = new FileReader();
    reader.onload = function() {
        if (!this.result.includes('application/pdf')) {
            swal("Only PDF Formatted Label allowed");
            return;
        }

        var pdf = this.result;
        var defaultSize = $('#id_label_size').val();
        labelSizeMatch(defaultSize, pdf).then(function (result) {
            addLabelImage(pdf);
        }).catch(function (error){
            swal(
                "Label size does not match",
                "The PDF uploaded does not match the required label size i.e. " + defaultSize,
                "warning"
            );
            return;
        });
    };
    reader.readAsDataURL(this.files[0]);
});

$('#approved-label-mockup').on('click', function(e) {
    e.preventDefault();
    addLabelImage($(this).attr('href'));
});

var mockupItems = $('#mockup-editor .previews img').on('click', function() {
    var mockupIndex = mockupItems.index(this);
    $('#save-mockup').attr('mockup-index', mockupIndex).removeClass('hidden');

    MockupEditor.setDimensions(MockupEditor.labelMockups[mockupIndex]);
    MockupEditor.loadCanvas();
    MockupEditor.generate();
});

$('#save-mockup').on('click', function(e) {
    e.preventDefault();
    var mockupIndex = $('#save-mockup').addClass('hidden').attr('mockup-index');
    MockupEditor.save(parseInt(mockupIndex));
});

$('#mockup-editor .btn-index').on('click', '.btn', function(e) {
    e.preventDefault();
    $('#mockup-editor .btn-index .btn').not(this).removeClass('active');

    $(this).toggleClass('active');
    if ($(this).hasClass('active')) {
        MockupEditor.controlIndex = $('#mockup-editor .btn-index .btn').index(this);
    } else {
        MockupEditor.controlIndex = null;
    }

    $(this).trigger('blur');
});

$('#mockup-editor .btn-control').on('click', '.btn', function(e) {
    e.preventDefault();
    $('#mockup-editor .btn-control .btn').toggleClass('active');
    // $(this).toggleClass('active');
    MockupEditor.control = $('#mockup-editor .btn-control .active').data('type');
    $(this).trigger('blur');
});

$('#save-mockups').on('click', function(e) {
    e.preventDefault();
    e.stopPropagation();

    var selectedMockups = $('.previews .mockup-item [type="checkbox"]:checked + img');
    selectedMockups.each(function() {
        mockupsUploader.addFile(MockupEditor.dataURLtoFile(this.src, $(this).attr('id') + 'img.png'));
    });
    var labelInput = $('#modal-mockup-images [type="file"]').get(0);
    if (labelInput.files.length) {
        mockupsUploader.addFile(labelInput.files[0]);
    }

    if (selectedMockups.length === 0) {
        swal('Select one mockup to save with your label');
    } else {
        $('[name="mockup_urls"]').remove();
        $(window.plupload_Config.saveFormID).trigger("cleanmockups");
        $('#modal-mockup-images .modal-content').addClass('loading');
        $('.mockup-save-progress').addClass('show');
        $(this).prop('disabled', true);
        $('[name="label_presets"]').val(JSON.stringify(MockupEditor.labelMockups));
        mockupsUploader.start();
    }
});

var mockupsUploader = new plupload.Uploader({
    runtimes: 'html5',
    browse_button: document.getElementById('save-mockups'),

    url: window.plupload_Config.url,
    file_name_name: false,
    multipart: true,
    multipart_params: {
        filename: 'filename',
        utf8: true,
        AWSAccessKeyId: window.plupload_Config.AWSAccessKeyId,
        acl: "public-read",
        policy: window.plupload_Config.policy,
        signature: window.plupload_Config.signature,
        key: window.plupload_Config.key,
        'Content-Type': 'image/jpeg',
    },
    filters: {
        max_file_size: '100mb',
    },
    init: {
        PostInit: function(up) {
            up.disableBrowse();
        },
        BeforeUpload: function(up, file) {
            var params = up.settings.multipart_params;
            params['Content-Type'] = file.type;

            if (params['Content-Type'].indexOf('image/') > -1) {
                params.policy = window.plupload_Config.imgPolicy;
                params.signature = window.plupload_Config.imgSignature;
            } else {
                params.policy = window.plupload_Config.policy;
                params.signature = window.plupload_Config.signature;
            }
            var randomPrefix = (window.crypto.getRandomValues(new Uint32Array(1))[0]).toString(16);
            var ext = file.name.split('.').pop();
            var filename = 'supplement_' + randomPrefix + '.' + ext;
            params.key = window.plupload_Config.key.replace('${filename}', filename);
        },
        FilesAdded: function(up, files) {
            files.forEach(function(file) {
                var progressBar = $('.mockup-save .progress-bar.clone').clone();
                progressBar.removeClass('clone');
                progressBar.attr('upload-id', file.id);
                $('.mockup-save-progress').append(progressBar);
            });
        },
        UploadProgress: function(up, file) {
            var progressBar = $('.mockup-save-progress [upload-id="' + file.id + '"]');
            var percent = (file.percent / up.files.length) + '%';
            progressBar.css('width', percent).find('.sr-only').text(percent);
        },
        FileUploaded: function(up, file, info) {
            var key = up.settings.multipart_params.key;
            var url = window.plupload_Config.url + key;
            var ext = url.split('.').pop();
            if (ext === 'pdf') {
                // Add label
                $('[name="upload_url"]').val(url);
                $(window.plupload_Config.saveFormID).trigger("addlabel", [url]);
            } else {
                // Add image
                $(window.plupload_Config.saveFormID).append(
                    $('<input type="hidden" name="mockup_urls">').val(url)
                );
                $(window.plupload_Config.saveFormID).trigger("addmockups", [url]);
            }
        },
        UploadComplete: function(up, files) {
            $('.mockup-save-progress').removeClass('show').empty();
            $('#modal-mockup-images .modal-content').removeClass('loading');
            $('#save-mockups').prop('disabled', false);
            $('#modal-mockup-images').modal('hide');
            mockupsUploader.splice();
        }
    }
});
mockupsUploader.init();

var currentLabel = $('[name="current_label"]').val();
if (currentLabel) {
    addLabelImage('https://app.dropified.com/api/ali/get-image?' + $.param({url: currentLabel}));
}
