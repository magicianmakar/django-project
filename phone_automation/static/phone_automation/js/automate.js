var menuBlockTypes = [
    'flow-block-menu-number-one',
    'flow-block-menu-number-two',
    'flow-block-menu-number-three',
    'flow-block-menu-number-four',
    'flow-block-menu-number-five',
    'flow-block-menu-number-six',
    'flow-block-menu-number-seven',
    'flow-block-menu-number-eight',
    'flow-block-menu-number-nine',
    'flow-block-menu-number-zero',
];
var defaultBlockTypes = [
    'flow-block-greeting',
    'flow-block-menu',
    'flow-block-record',
    'flow-block-dial',
];
var allBlockTypes = {
    'flow-block-menu-number-one': {'title': '1'},
    'flow-block-menu-number-two': {'title': '2'},
    'flow-block-menu-number-three': {'title': '3'},
    'flow-block-menu-number-four': {'title': '4'},
    'flow-block-menu-number-five': {'title': '5'},
    'flow-block-menu-number-six': {'title': '6'},
    'flow-block-menu-number-seven': {'title': '7'},
    'flow-block-menu-number-eight': {'title': '8'},
    'flow-block-menu-number-nine': {'title': '9'},
    'flow-block-menu-number-zero': {'title': '0'},

    'flow-block-greeting': {'icon': 'fa fa-comment-o', 'title': 'Play a Message'},
    'flow-block-menu': {'icon': 'fa fa-list-ol', 'title': 'Play Menu Options'},
    'flow-block-record': {'icon': 'fa fa-microphone', 'title': 'Record a Voicemail'},
    'flow-block-dial': {'icon': 'fa fa-forward', 'title': 'Forward to a Phone Number'}
};



Vue.component('block-type-selection', {
    template: '#block-type-selection-tpl',
    props: ['model', 'bus', 'blockTypes'],
    methods: {
        changeBlockType: function(blockType) {
            this.model.block_type = blockType;
            this.bus.$emit('update-block', this.model);
        }
    }
});

Vue.component('block-type-selection-menu', {
    template: '#block-type-selection-menu-tpl',
    props: ['model', 'bus', 'blockTypes'],
    methods: {
        changeBlockType: function(blockType) {
            this.model.block_type = blockType;
            this.bus.$emit('update-block', this.model);
        }
    }
});

Vue.component('mp3-upload', {
    template: '#mp3-upload-tpl',
    props: ['model', 'bus'],
    data: function() {
        return {
            isUploading: false
        };
    },
    created: function() {
        if (!this.model.config.mp3) {
            Vue.set(this.model.config, 'mp3', '');
        }
    },
    computed: {
        isSaving: function() {
            return this.isUploading;
        }
    },
    methods: {
        removeUploadedFile: function() {
            var updatedBlock = $.extend(true, this.model, {
                config: {
                    mp3: ''
                }
            });
            this.bus.$emit('update-block', updatedBlock);
        },
        fileChange: function(event) {
            this.isUploading = true;
            var that = this;
            var formData = new FormData();
            // add assoc key values, this will be posts values
            var file = event.target.files[0];
            formData.append("mp3", file, file.name);
            formData.append("step", this.model.step);

            $.ajax({
                url: uploadUrl,
                type: 'POST',
                data: formData,
                contentType: false,
                processData: false,
                success: function(data) {
                    if (data.status) {
                        that.model.config.mp3 = data.url;
                    }
                },
                error: function(data) {
                    displayAjaxError('Saving call automation', data);
                },
                complete: function() {
                    that.isUploading = false;
                }
            });
            // this.isUploading = false;
        }
    }
});

Vue.component('add-new-block', {
    template: '#add-new-block-tpl',
    props: ['position', 'parent', 'parent_type', 'bus'],
    methods: {
        addChild: function() {
            this.bus.$emit('create-block', this.position, this.parent, {});
        }
    }
});

Vue.component('flow-block-basic-message', {
    template: '#flow-block-basic-message-tpl',
    props: ['model', 'bus', 'enableNoMessage'],
    created: function() {
        if (!this.model.config.no_message) {
            Vue.set(this.model.config, 'no_message', false);
        }
    },
    data: function() {
        var active = 'say';
        if (this.model.config.mp3) {
            active = 'mp3';
        } else if (this.model.config.no_message) {
            active = 'no_message';
        }
        return {
            active: active
        };
    },
    methods: {
        activateNav: function(e, type) {
            e.preventDefault();

            this.active = type;
            if (type == 'mp3') {
                this.model.config.say = '';
                this.model.no_message = false;
            } else if (type == 'say') {
                this.model.config.mp3 = '';
                this.model.no_message = false;
            } else if (type == 'no_message') {
                var updatedBlock = $.extend(true, this.model, {
                    config: {
                        say: '',
                        mp3: '',
                        no_message: true
                    }
                });

                this.bus.$emit('update-block', updatedBlock);
            }
        }
    }
});


var notMenuMixin = {
    created: function() {
        Vue.delete(this.model.config, 'children_block_types');
        Vue.delete(this.model.config, 'block_selection');
        Vue.delete(this.model.config, 'without_options');
        Vue.set(this.model, 'children', []);
    }
};
Vue.component('flow-block-greeting', {
    template: '#flow-block-greeting-tpl',
    mixins: [notMenuMixin],
    props: ['model', 'bus'],
    created: function() {
        // Change necessary config options
        var updatedBlock = $.extend(true, this.model, {
            config: {
                have_next: true,
                voice: this.model.config.voice || 'alice'
            }
        });

        this.bus.$emit('update-block', updatedBlock);
    }
});
Vue.component('flow-block-record', {
    template: '#flow-block-record-tpl',
    mixins: [notMenuMixin],
    props: ['model', 'bus'],
    created: function() {
        // Change necessary config options
        if (!this.model.config.play_beep) {
            Vue.set(this.model.config, 'play_beep', true);
        }

        var updatedBlock = $.extend(true, this.model, {
            config: {
                have_next: false
            }
        });

        this.bus.$emit('update-block', updatedBlock);
    },
    methods: {
        toggleBeep: function(e) {
            e.preventDefault();
            this.model.config.play_beep = !this.model.config.play_beep;
            this.bus.$emit('update-block', this.model);
        }
    }
});
Vue.component('flow-block-menu', {
    template: '#flow-block-menu-tpl',
    props: ['model', 'bus'],
    data: function() {
        return {
            childrenBlockTypes: this.getChildrenBlockTypes(),
            selectedDigit: menuBlockTypes[0]
        };
    },
    created: function() {
        Vue.set(this.model.config, 'children_block_types', {});
        Vue.set(this.model.config, 'block_selection', 'block-type-selection-menu');
        if (!this.model.config.repeat) {
            Vue.set(this.model.config, 'repeat', false);
        }

        // Change necessary config options
        var updatedBlock = $.extend(true, this.model, {
            config: {
                is_parent: true,
                can_add_children: false,
                voice: this.model.config.voice || 'alice',
                have_next: true,
                children_block_types: this.childrenBlockTypes
            }
        });
        this.bus.$emit('update-block', updatedBlock);
    },
    updated: function() {
        this.model.config.children_block_types = this.getChildrenBlockTypes();
        this.bus.$emit('update-block', this.model);
    },
    methods: {
        selectDigit: function(e, digitBlockType) {
            e.preventDefault();
            this.selectedDigit = digitBlockType;
        },
        deleteDigit: function(e, blockType) {
            e.preventDefault();
            for (var i = 0, iLength = this.model.children.length; i < iLength; i++) {
                var childrenDigit = this.model.children[i];
                if (childrenDigit.block_type == blockType) {
                    this.bus.$emit('delete-block', childrenDigit);
                    break;
                }
            }
            this.childrenBlockTypes = this.getChildrenBlockTypes();
        },
        createBlockType: function(e, childrenBlockType, blockType) {
            e.preventDefault();
            var baseBlock = {
                block_type: childrenBlockType,
                config: {
                    is_parent: true,
                    can_add_children: true,
                    have_next: true,
                    number: parseInt(allBlockTypes[childrenBlockType].title)
                }
            };
            var index = this.childrenBlockTypes.indexOf(childrenBlockType);
            this.childrenBlockTypes.splice(index, 1);
            this.bus.$emit('create-block', this.model.children.length, this.model.step, baseBlock);

            var childrenBaseBlock = {
                block_type: blockType,
                config: {
                    is_parent: true,
                    can_add_children: false,
                    have_next: true,
                    number: null
                }
            };
            var parentBlock = this.model.children[this.model.children.length - 1];
            this.bus.$emit('create-block', 0, parentBlock.step, childrenBaseBlock);
        },
        toggleRepeat: function(e) {
            e.preventDefault();
            this.model.config.repeat = !this.model.config.repeat;
            this.bus.$emit('update-block', this.model);
        },
        getChildrenBlockTypes: function() {
            var newChildrenBlockTypes = menuBlockTypes.slice();
            for (var i = 0, iLength = this.model.children.length; i < iLength; i++) {
                var children = this.model.children[i];
                if (children.block_type) {
                    var index = newChildrenBlockTypes.indexOf(children.block_type)
                    if (index > -1) {
                        newChildrenBlockTypes.splice(index, 1);
                    }
                }
            }
            return newChildrenBlockTypes;
        },
        createOption: function(e) {
            e.preventDefault();
            var baseBlock = {
                config: {
                    is_parent: true,
                    can_add_children: true,
                    have_next: true,
                    number: null
                }
            };
            this.bus.$emit('create-block', this.model.children.length, this.model.step, baseBlock);
        },
        removeChildren: function(e, number) {
            e.preventDefault();

            for (var i = 0, iLength = this.model.children.length; i < iLength; i++) {
                var child = this.model.children[i];
                if (child.config.number == number) {
                    this.bus.$emit('delete-block', child);
                    break;
                }
            }
        }
    }
});
var flowBlockMenuNumberMixin = {
    template: '#flow-block-menu-number-tpl',
    props: ['model', 'bus'],
    data: function() {
        return {
            number: 0
        };
    },
    created: function() {
        // Change necessary config options
        Vue.set(this.model.config, 'without_options', true);

        var updatedBlock = $.extend(true, this.model, {
            config: {
                number: this.number,
                can_add_children: false
            }
        });

        this.bus.$emit('update-block', updatedBlock);
    }
};
Vue.component('flow-block-menu-number-one', { mixins: [flowBlockMenuNumberMixin], data: function() { return { number: 1 }; }});
Vue.component('flow-block-menu-number-two', { mixins: [flowBlockMenuNumberMixin], data: function() { return { number: 2 }; }});
Vue.component('flow-block-menu-number-three', { mixins: [flowBlockMenuNumberMixin], data: function() { return { number: 3 }; }});
Vue.component('flow-block-menu-number-four', { mixins: [flowBlockMenuNumberMixin], data: function() { return { number: 4 }; }});
Vue.component('flow-block-menu-number-five', { mixins: [flowBlockMenuNumberMixin], data: function() { return { number: 5 }; }});
Vue.component('flow-block-menu-number-six', { mixins: [flowBlockMenuNumberMixin], data: function() { return { number: 6 }; }});
Vue.component('flow-block-menu-number-seven', { mixins: [flowBlockMenuNumberMixin], data: function() { return { number: 7 }; }});
Vue.component('flow-block-menu-number-eight', { mixins: [flowBlockMenuNumberMixin], data: function() { return { number: 8 }; }});
Vue.component('flow-block-menu-number-nine', { mixins: [flowBlockMenuNumberMixin], data: function() { return { number: 9 }; }});
Vue.component('flow-block-menu-number-zero', { mixins: [flowBlockMenuNumberMixin], data: function() { return { number: 0 }; }});
Vue.component('flow-block-dial', {
    template: '#flow-block-dial-tpl',
    mixins: [notMenuMixin],
    props: ['model', 'bus'],
    created: function() {
        // Change necessary config options
        var updatedBlock = $.extend(true, this.model, {
            config: {
                have_next: false
            }
        });

        this.bus.$emit('update-block', updatedBlock);
    }
});

// define the item component
Vue.component('item', {
  template: '#action-tpl',
  props: {
    model: Object,
    bus: Object,
    blockTypes: {
        type: Object,
        default: defaultBlockTypes
    },
    blockSelectionComponent: {
        type: String,
        default: 'block-type-selection'
    }
  },
  data: function () {
    return {
        selectedBlockData: allBlockTypes[this.model.block_type] || {}
    };
  },
  watch: {
    'model.block_type': function(newValue, oldValue) {
        this.selectedBlockData = allBlockTypes[this.model.block_type];
    }
  },
  computed: {
    updateBlock: function(newBlock) {
        this.model = newBlock;
    },
    hasChildren: function () {
        return this.model && this.model.config.is_parent;
    },
    getAvailableChildren: function () {
        var availableChildren = [];
        for (var i = 0, iLenght = this.model.children.length; i < iLenght; i++) {
            var children = this.model.children[i];
            availableChildren.push(children);
            if (!children.config.have_next) {
                break;
            }
        }
        return availableChildren;
    }
  },
  methods: {
    deleteBlock: function() {
        this.bus.$emit('delete-block', this.model);
    }
  }
});

// boot up the demo
var demo = new Vue({
    el: '#call-flow',
    data: {
        treeData: data,
        bus: new Vue()
    },
    created: function() {
        this.bus.$on('create-block', this.createBlock);
        this.bus.$on('update-block', this.updateBlock);
        this.bus.$on('delete-block', this.deleteBlock);
        this.addFirstNode(this.treeData[0]);
    },
    computed: {
        getAvailableChildren: function () {
            var availableChildren = [];
            for (var i = 0, iLenght = this.treeData.length; i < iLenght; i++) {
                var children = this.treeData[i];
                availableChildren.push(children);
                if (!children.config.have_next) {
                    break;
                }
            }
            return availableChildren;
        }
    },
    methods: {
        save: function(e) {
            e.preventDefault();
            $.ajax({
                url: save.url,
                type: 'POST',
                data: {
                    first_step: this.first_node,
                    last_step: nodeCount,
                    children: JSON.stringify(this.treeData)
                },
                success: function(data) {
                    if (data.status) {
                        window.location.href = save.redirect;
                    }
                },
                error: function(data) {
                    displayAjaxError('Saving call automation', data);
                }
            });
        },
        addFirstNode: function(node) {
            if (node && node.step) {
                this.first_node = node.step;
            }
        },
        updateBlock: function(updatedBlock) {
            foundParentNode = this.findNode({step: 0, children: this.treeData}, updatedBlock.parent);
            for (var i = 0, iLength = foundParentNode.children.length; i < iLength; i++) {
                var node = foundParentNode.children[i];
                if (node.step == updatedBlock.step) {
                    foundParentNode.children[i] = updatedBlock;
                    break;
                }
            }
        },
        deleteBlock: function(deletedBlock) {
            foundParentNode = this.findNode({step: 0, children: this.treeData}, deletedBlock.parent);
            for (var i = 0, iLength = foundParentNode.children.length; i < iLength; i++) {
                var node = foundParentNode.children[i];
                if (node.step == deletedBlock.step) {
                    var nodeStepReplacement = null;
                    var nextNodeIndex = i + 1;
                    if (iLength > nextNodeIndex) {
                        nodeStepReplacement = foundParentNode.children[nextNodeIndex].step;
                    }

                    if (foundParentNode.next_step == deletedBlock.step) {
                        foundParentNode.next_step = nodeStepReplacement;
                    } else if (i > 0) {
                        foundParentNode.children[i - 1].next_step = nodeStepReplacement;
                    } else if (this.first_node == deletedBlock.step) {
                        this.addFirstNode({step: nodeStepReplacement});
                    }

                    foundParentNode.children.splice(i, 1);
                    break;
                }
            }
        },
        createBlock: function(position, parent, baseBlock) {
            nodeCount += 1;
            var newNode = $.extend(true, {
                block_type: '',
                step: nodeCount,
                parent: parent,
                next_step: null,
                children: [],
                config: {
                    is_parent: false,
                    have_next: true,
                    can_add_children: false
                }
            }, baseBlock);
            foundNode = this.findNode({step: 0, children: this.treeData}, parent);
            // Move previous node forward
            if (position == 0) {
                if (foundNode.config && foundNode.config.can_add_children) {
                    foundNode.next_step = nodeCount;
                }
            } else {
                if (foundNode.config.can_add_children) {
                    foundNode.children[position - 1].next_step = newNode.step;
                }
            }

            if (newNode.config.have_next) {
                newNode.next_step = foundNode.children.length == position ? null : foundNode.children[position].step;
            }
            // Replace previous node position
            foundNode.children.splice(position, 0, newNode);

            if (parent == 0 && position == 0) {
                this.addFirstNode(newNode);
            }
        },
        findNode: function(element, nodeStep) {
            if(element.step == nodeStep) {
                return element;
            } else if (element.children != null) {
                var result = null;
                for (var i = 0, iLength = element.children.length; result == null && i < iLength; i++){
                    result = this.findNode(element.children[i], nodeStep);
                }
                return result;
            }
            // return null;
        }
    }
});
