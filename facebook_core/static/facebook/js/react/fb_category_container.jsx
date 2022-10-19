/* global $, product, product:true, displayAjaxError, FBCategorySpecifics */
(function (variantsConfig) {
    'use strict';

    const e = React.createElement;
    const TIMEOUT_BETWEEN_CATEGORY_SEARCHES = 1000;

    class FBCategorySelector extends React.Component {

        constructor(props) {
            super(props);
            if (product.fb_category_id === 0 || product.fb_category_id === '0') {
                product.fb_category_id = ''
            }
            if (product.fb_category_name === null || product.fb_category_name === undefined) {
                product.fb_category_name = ''
            }
            let category_Search_Term = productDetails?.producttype ?? '';
            if (category_Search_Term.match(' ')) {
                category_Search_Term = category_Search_Term.split(' ').slice(-1).toString();
            }
            const categorySearchTerm = category_Search_Term;
            const fbCategoryId = product.fb_category_id;
            const fbCategoryName = product.fb_category_name;
            this.state = {
                fbCategoryId,
                fbCategoryName,
                categorySearchTerm,
                categoryOptions: [],
                fieldsToHide: variantsConfig?.map(el => el?.title?.replace(' ', '')?.toLowerCase()),
                isLoading: false,
            };
        }

        componentDidMount() {
            const { fbCategoryId, fbCategoryName } = this.state;
            var self = this;
            $('.fb-category').select2({
                placeholder: 'Select a category',
                ajax: {
                    url: api_url('search-categories', 'fb'),
                    delay: TIMEOUT_BETWEEN_CATEGORY_SEARCHES,
                    dataType: 'json',
                    data: function (params) {
                        return {
                            'search_term':  params.term,
                            'store_index': product.fb_store_index,
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

                product.fb_category_id = data.id;
                product.fb_category_name = data.text;
                self.setState({
                    fbCategoryId: data.id,
                    fbCategoryName: data.text,
                });
            });
            if (fbCategoryId) {
                var option = $('<option selected>' + fbCategoryName + '</option>').val(fbCategoryId);
            }
            $('.fb-category').append(option).trigger('change');
        }

        getCategorySpecifics() {
            const { categoryOptions, fbCategoryId } = this.state;
            return categoryOptions.find(({ id }) => id == fbCategoryId)?.attributes ?? [];
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
                            <label htmlFor="fb-category" style={{width: '100%'}} className="control-label">
                                Facebook Category <span style={{color: '#ed5565'}}>*</span>
                            </label>
                            <select className="fb-category" id="fb-category"
                                    data-value={categorySearchTerm} required>
                            </select>
                        </div>
                    </div>
                    <div className="row">
                        <FBCategorySpecifics
                            specifics={this.getCategorySpecifics()}
                            fieldsToHide={fieldsToHide}
                        />
                    </div>
                </React.Fragment>
            );
        }
    }

    const domContainer = document.querySelector('#fb-category-container');
    ReactDOM.render(<FBCategorySelector/>, domContainer);
}(variantsConfig));
