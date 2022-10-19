/* global $, toastr, swal, displayAjaxError */

(function(store_id, sub_conf) {
'use strict';

Vue.component('google-import-status-indicator', {
    template: '#products-import-status-indicator-tpl',
    props: {},
    data: function() {
        return {
            currentStatus: 'Loading',
            lastSyncedDate: null,
            loadStatusInterval: null,
        };
    },
    computed: {
        computedStatus: function() {
            var computedStatus = '';
            $('#start-new-import-button').prop('disabled', false);
            var last_updated_date = '';
            if (this.lastSyncedDate) {
                var date = new Date(this.lastSyncedDate);
                var date_options = {year: 'numeric', month: 'short', day: 'numeric'};
                last_updated_date = 'Last Updated on ' +
                            date.toLocaleDateString(undefined, date_options) + ' at ' +
                            date.toLocaleString(undefined, { hour: 'numeric', minute: 'numeric' });
            }
            switch (this.currentStatus) {
                case 'Finished':
                    computedStatus = last_updated_date;
                    break;

                case 'Import in Progress':
                    $('#start-new-import-button').prop('disabled', true);
                    computedStatus = 'Import in progress. It may take a few minutes for products to get imported.';
                    if (last_updated_date) {
                        computedStatus += ' (' + last_updated_date + ')';
                    }
                    break;

                default:
                    computedStatus = this.currentStatus;
                    break;
            }

            return computedStatus;
        },
    },
    methods: {
        loadStatus: function() {
            var vm = this;

            $.ajax({
                url: api_url('import-products-status', 'google'),
                type: 'GET',
                data: { store: store_id },
                success: function(resp) {
                    vm.currentStatus = resp.data.status;
                    vm.lastSyncedDate = resp.data.last_updated;
                    if (resp.data.status === 'Finished' && vm.loadStatusInterval) {
                        clearInterval(vm.loadStatusInterval);
                        vm.loadStatusInterval = null;

                        toastr.success('Successfully loaded Google products.', 'Google Products Import');

                        setTimeout(function() {
                            window.location.reload();
                        }, 1000);
                    }
                },
                error: function(data) {
                    displayAjaxError('Google Products Import', data);
                }
            });
        },
        initImportButton: function() {
            var vm = this;
            $('#start-new-import-button').on('click', function (e) {
                var btn = $('#start-new-import-button');
                btn.bootstrapBtn('loading');
                $.ajax({
                    url: api_url('new-products-import-job', 'google'),
                    type: 'POST',
                    data: {
                        store: user_filter.store,
                    },
                    context: {el: $(this)},
                    success: function (data) {
                        btn.bootstrapBtn('reset');
                        toastr.info('Successfully submitted an import request. It may take a few minutes for products to get imported.', 'Google Products Import');
                        vm.loadStatus();
                        vm.loadStatusInterval = setInterval(function() {
                            vm.loadStatus();
                        }, 10000);
                    },
                    error: function (data) {
                        btn.bootstrapBtn('reset');
                        displayAjaxError('Google Products Import', data);
                    }
                });
            });
        }
    },
    destroyed: function() {
        clearInterval(vm.loadStatusInterval);
        vm.loadStatusInterval = null;
    }
});

// create the root instance
var vue = new Vue({
    el: '#google-import-status-wrapper'
});

vue.$refs.googleImportStatusIndicator.initImportButton();
vue.$refs.googleImportStatusIndicator.loadStatus();

})(user_filter.store, sub_conf);