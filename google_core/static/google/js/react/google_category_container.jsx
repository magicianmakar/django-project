/* global $, product, product:true, displayAjaxError, GoogleCategorySpecifics */
(function (variantsConfig) {
    'use strict';

    const e = React.createElement;
    const TIMEOUT_BETWEEN_CATEGORY_SEARCHES = 1000;

    class GoogleCategorySelector extends React.Component {

        constructor(props) {
            super(props);
            if (product.google_category_id === 0 || product.google_category_id === '0') {
                product.google_category_id = ''
            }
            if (product.google_category_name === null || product.google_category_name === undefined) {
                product.google_category_name = ''
            }
            const categorySearchTerm = productDetails?.producttype ?? '';
            const googleCategoryId = product.google_category_id;
            const googleCategoryName = product.google_category_name;
            this.state = {
                googleCategoryId,
                googleCategoryName,
                categorySearchTerm,
                categoryOptions: [],
                fieldsToHide: variantsConfig?.map(el => el?.title?.replace(' ', '')?.toLowerCase()),
                isLoading: false,
            };
        }

        componentDidMount() {
            const { googleCategoryId, googleCategoryName } = this.state;
            var self = this;
            $('.google-category').select2({
                placeholder: 'Select a category',
                ajax: {
                    url: api_url('search-categories', 'google'),
                    delay: TIMEOUT_BETWEEN_CATEGORY_SEARCHES,
                    dataType: 'json',
                    data: function (params) {
                        return {
                            'search_term':  params.term,
                            'store_index': product.google_store_index,
                        };
                    },
                    processResults: function (response) {
                        var categories = response.data?.categories ?? [];
                        self.setState({
                            categoryOptions: categories,
                        });
                        return {
                            results: categories.map(function(item) {
                                return {
                                    id: item.id,
                                    text: item.name,
                                }
                            })
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

                product.google_category_id = data.id;
                product.google_category_name = data.text;
                self.setState({
                    googleCategoryId: data.id,
                    googleCategoryName: data.text,
                });
            });
            if (googleCategoryId) {
                var option = $('<option selected>' + googleCategoryName + '</option>').val(googleCategoryId);
            }
            $('.google-category').append(option).trigger('change');
        }

        getCategorySpecifics() {
            const { categoryOptions, googleCategoryId } = this.state;
            return categoryOptions.find(({ id }) => id == googleCategoryId)?.attributes ?? [];
        }

        render() {
            const {
                categorySearchTerm,
                fieldsToHide,
            } = this.state;
            return (
                <React.Fragment>
                    <div className="row">
                        <div className='form-group col-xs-12'>
                            <label htmlFor="google-category" style={{width: '100%'}} className="control-label">
                                Google Category <span style={{color: '#ed5565'}}>*</span>
                            </label>
                            <select className="google-category" id="google-category"
                                    data-value={categorySearchTerm} required>
                            </select>
                        </div>
                    </div>
                    <div className="row">
                        <GoogleCategorySpecifics
                            specifics={this.getCategorySpecifics()}
                            fieldsToHide={fieldsToHide}
                        />
                    </div>
                </React.Fragment>
            );
        }
    }

    const domContainer = document.querySelector('#google-category-container');
    ReactDOM.render(<GoogleCategorySelector/>, domContainer);
}(variantsConfig));
