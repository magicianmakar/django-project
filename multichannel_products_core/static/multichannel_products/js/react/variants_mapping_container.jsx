/* global $, master_variants, connected_stores, displayAjaxError */
(function (master_variants, connected_stores) {
    'use strict';

    const e = React.createElement;

    const WarningModal = ({isShowingModal, onCancel, onConfirm}) => {

        React.useEffect(() => {
            if (isShowingModal) {
                $('#warning-modal').modal('show');
            } else {
                $('#warning-modal').modal('hide');
            }
        }, [isShowingModal])
        return (
            <div id="warning-modal" className="modal fade" aria-hidden="true">
                <div className="modal-dialog" style={{maxWidth: '30%'}}>
                    <div className="modal-content">
                        <div className="modal-body" style={{fontSize: '16px'}}>
                            <span>All of your changes will be lost on store change.</span>
                            <br/>
                            <span>Do you wish to continue?</span>
                        </div>
                        <div className="modal-footer">
                            <button type="button" className="btn btn-outline btn-default pull-left"
                                    onClick={() => onCancel()}
                                    data-dismiss="modal">
                                Cancel
                            </button>
                            <button className="btn btn-primary add-supplier-info-btn" type="button"
                                    onClick={() => onConfirm()}
                            >
                                Yes
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        )
    };

    class VariantsMappingSelector extends React.Component {
        constructor(props) {
            super(props);
            this.state = {
                store: {id: null, type: '', title: '', variants_map: []},
                isChanged: false,
                isShowingModal: false,
                changedStore: null,
            };
            this.handleStoreSelectionChange = this.handleStoreSelectionChange.bind(this);
            this.handleVariantSelectionChange = this.handleVariantSelectionChange.bind(this);
            this.handleStoreSelectionChangeWrapper = this.handleStoreSelectionChangeWrapper.bind(this);

            this.onCancel = this.onCancel.bind(this);
            this.onConfirm = this.onConfirm.bind(this);

            this.handleSave = this.handleSave.bind(this);
        }

        componentDidMount() {
            if (connected_stores) {
                this.setState({store: connected_stores[0]})
            }
        }

        handleStoreSelectionChangeWrapper(newStore) {
            const {isChanged} = this.state;
            if (isChanged) {
                this.setState({
                    isShowingModal: true,
                    changedStore: newStore,
                })
            } else {
                this.handleStoreSelectionChange(newStore)
            }
        }

        onCancel() {
            this.setState({
                isShowingModal: false,
                changedStore: null,
            })
        }

        onConfirm() {
            const {changedStore} = this.state;
            this.handleStoreSelectionChange(changedStore)
        }

        handleStoreSelectionChange(newStore) {
            if (newStore === 'Select a store') {
                this.setState({
                    store: {id: null, type: '', title: '', variants_map: []},
                    isChanged: false,
                    isShowingModal: false,
                    changedStore: null,
                });
            } else {
                const value = newStore.split('_')
                this.setState({
                    store: connected_stores.find(item => String(item.id) === value[0] && item.type === value[1]),
                    isChanged: false,
                    isShowingModal: false,
                    changedStore: null,
                });
            }
        }

        handleVariantSelectionChange(childVariant, masterVariant) {
            const {store} = this.state;
            this.setState({
                store: {...store, variants_map: {...store.variants_map, [childVariant]: masterVariant}},
                isChanged: true,
            });
        }

        handleSave() {
            $.ajax({
                url: api_url('variants-mapping', 'multichannel'),
                type: 'POST',
                data: JSON.stringify({
                    master_product: product_id,
                    child_data: this.state.store,
                }),
                contentType: "application/json; charset=utf-8",
                dataType: "json",
                context: {
                    btn: $(this)
                },
                success: function (data) {
                    if (data.status === 'ok') {
                        toastr.success('Variants Mapping', 'Mapping Saved');

                        // setTimeout(function () {
                        //     window.location.reload();
                        // }, 500);
                    } else {
                        displayAjaxError('Variants Mapping', data);
                    }
                },
                error: function (data) {
                    displayAjaxError('Variants Mapping', data);
                },
                // complete: function () {
                //     this.btn.bootstrapBtn('reset');
                // }
            });
        }

        render() {
            const {store, isShowingModal} = this.state;
            return (
                <React.Fragment>
                    <div className="row">
                        <div className='form-group col-xs-12'>
                            <label htmlFor='store-select'>Store</label>
                            <select
                                id='store-select'
                                value={store.id + "_" + store.type}
                                className='form-control'
                                placeholder='Select a store'
                                onChange={({target: {value}}) => this.handleStoreSelectionChangeWrapper(value)}
                            >
                                <option key='default-option'>
                                    Select a store
                                </option>
                                {
                                    connected_stores?.map(store => (
                                        <option key={store.id} value={store.id + "_" + store.type}>
                                            {store.title}
                                        </option>
                                    ))
                                }
                            </select>
                        </div>
                    </div>
                    {store.id && (
                        <React.Fragment>
                            <div className="row">
                                <div className="col-xs-12">
                                    <table className="table table-compact">
                                        <thead>
                                        <tr>
                                            <th>{store.title}</th>
                                            <th style={{textAlign: 'right', minWidth: '200px'}}>Multi-Channel</th>
                                        </tr>
                                        </thead>
                                        <tbody>
                                        {
                                            store.variants_data.map(item => (
                                                <tr key={item.title}>
                                                    <td className="variant-image" style={{width: '100%'}}>
                                                        {item.image ? (
                                                            <img className="thumb unveil" src={item.image}
                                                                 style={{width: '50px', marginRight: '10px'}}/>
                                                        ) : (
                                                            <img className="thumb"
                                                                 src='../../../../../static/img/blank.gif'/>
                                                        )}
                                                        <span>{item.title}</span>
                                                    </td>
                                                    <td>
                                                        <select className="variant-select form-control"
                                                                style={{width: 'auto', float: 'right'}}
                                                                value={store.variants_map[item.title]}
                                                                onChange={({target: {value}}) => this.handleVariantSelectionChange(item.title, value)}
                                                        >
                                                            <option key="none" value={null}>None</option>
                                                            {master_variants?.map(variant => (
                                                                <option key={variant} value={variant}>{variant}</option>
                                                            ))}
                                                        </select>
                                                    </td>
                                                </tr>
                                            ))
                                        }
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                            <div className="row">
                                <div className="col-md-6">
                                    <button id="save-mapping" className="btn btn-success" onClick={this.handleSave}>
                                        <i className="fa fa-save"></i> Save
                                    </button>
                                </div>
                            </div>
                        </React.Fragment>
                    )}
                    <WarningModal isShowingModal={isShowingModal} onCancel={this.onCancel} onConfirm={this.onConfirm}/>
                </React.Fragment>
            );
        }
    }

    const domContainer = document.querySelector('#variants-mapping-container');
    ReactDOM.render(<VariantsMappingSelector/>, domContainer);
}(master_variants, connected_stores));
