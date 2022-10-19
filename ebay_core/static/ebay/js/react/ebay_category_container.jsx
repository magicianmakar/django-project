/* global $, product, product:true, displayAjaxError, EbayCategorySpecifics */
(function (variantsConfig) {
    'use strict';

    const e = React.createElement;
    const TIMEOUT_BETWEEN_CATEGORY_SEARCHES = 1000;

    class EbayCategorySelector extends React.Component {

        constructor(props) {
            super(props);
            if (product.ebay_category_id === 0 || product.ebay_category_id === '0') {
                product.ebay_category_id = ''
            }
            const categorySearchTerm = productDetails?.producttype ?? '';
            const ebayCategoryId = product.ebay_category_id;
            this.state = {
                ebayCategoryId,
                categorySearchTerm,
                categoryOptions: [],
                categorySpecifics: null,
                fieldsToHide: variantsConfig?.map(el => el?.title?.replace(' ', '')?.toLowerCase()),
                isLoading: false,
            };
            this.handleGetCategorySpecificsResponse = this.handleGetCategorySpecificsResponse.bind(this);
        }

        componentDidMount() {
            const { ebayCategoryId } = this.state;
            var self = this;
            $('.ebay-category').select2({
                placeholder: 'Select a category',
                ajax: {
                    url: function (params) {
                        if (params.term && /^\d+$/.test(params.term)) {
                            return api_url('category-specifics', 'ebay');
                        } else {
                            return api_url('search-categories', 'ebay');
                        }
                    },
                    delay: TIMEOUT_BETWEEN_CATEGORY_SEARCHES,
                    dataType: 'json',
                    cache: true,
                    data: function (params) {
                        if (params.term && /^\d+$/.test(params.term)) {
                            return {
                                'category_id': params.term,
                                'site_id': product.ebay_site_id,
                            };
                        } else {
                            return {
                                'search_term': params.term,
                                'store_index': product.ebay_store_index,
                            };
                        }
                    },
                    processResults: function (response) {
                        if (response.data.categories) {
                            var categories = response.data.categories ? Object.values(response.data.categories) : [];
                            self.setState({
                                categoryOptions: response,
                            });
                            return {
                                results: categories.map(function (item) {
                                    return {
                                        id: item.id,
                                        text: item.name,
                                    }
                                })
                            };
                        } else if (response.data.data) {
                            return {
                                results: [
                                    {
                                        id: response.data.id,
                                        text: response.data.display_name,
                                    },
                                ]
                            };
                        }
                        return {
                            results: [],
                        };
                    },
                    allowClear: true,
                },
                templateResult: function (data, container) {
                    $(container).css('height', 'auto').css('margin', '0');
                    return data.text;
                }
            }).on('select2:select', function (e) {
                var data = e.params.data;

                product.ebay_category_id = data.id;
                self.setState({
                    ebayCategoryId: data.id,
                });
                self.getCategorySpecifics();
            });
            if (ebayCategoryId) {
                self.getCategorySpecifics();
                setTimeout(function () {
                    const { categorySpecifics } = self.state;
                    var option = new Option(categorySpecifics ? categorySpecifics.display_name : ebayCategoryId, ebayCategoryId, true, true)
                    $('.ebay-category').append(option).trigger('change');
                }, 1000)
            }
        }

        getCategorySpecifics() {
            const { ebayCategoryId } = this.state;
            const data = {
                'category_id': ebayCategoryId,
                'site_id': product.ebay_site_id,
            };
            $.ajax({
                url: api_url('category-specifics', 'ebay'),
                type: 'GET',
                data: data,
                success: this.handleGetCategorySpecificsResponse,
                error: function (data) {
                    displayAjaxError('eBay Category Options', data);
                }
            });
        }

        handleGetCategorySpecificsResponse(response) {
            const categorySpecifics = 'data' in response ? response.data : null
            this.setState({
                categorySpecifics: categorySpecifics
            });
        }

        render() {
            const {
                categorySearchTerm,
                categorySpecifics,
                fieldsToHide,
            } = this.state;
            return (
                <React.Fragment>
                    <div className="row">
                        <div className='form-group col-xs-12'>
                            <label htmlFor="ebay-category" style={{width: '100%'}} className="control-label">
                                eBay Category <span style={{color: '#ed5565'}}>*</span>
                            </label>
                            <select className="ebay-category" id="ebay-category"
                                    data-value={categorySearchTerm} required>
                            </select>
                        </div>
                        { categorySpecifics?.data && !categorySpecifics?.data.variationsEnabled &&
                        <div className='col-xs-12'>
                            <div className="alert alert-warning" role="alert" style={{ width: 'fit-content' }}>
                                <i className="fa fa-exclamation-triangle"/>&nbsp;
                                Variants are not supported in selected category.
                            </div>
                        </div>}
                    </div>
                    <div className="row">
                        <EbayCategorySpecifics
                            specifics={categorySpecifics?.data?.specifics}
                            fieldsToHide={fieldsToHide}
                        />
                    </div>
                </React.Fragment>
            );
        }
    }

    const domContainer = document.querySelector('#ebay-category-container');
    ReactDOM.render(<EbayCategorySelector/>, domContainer);
}(variantsConfig));
