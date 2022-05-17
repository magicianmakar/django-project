/* global $, product, product:true, displayAjaxError, FBCategorySpecifics */
(function (variantsConfig) {
    'use strict';

    const e = React.createElement;
    const TIMEOUT_BETWEEN_CATEGORY_SEARCHES = 1000;

    class FBCategorySelector extends React.Component {
        searchCategoryTimeout;

        constructor(props) {
            super(props);
            if (product.fb_category_id === 0 || product.fb_category_id === '0') {
                product.fb_category_id = ''
            }
            const categorySearchTerm = productDetails?.producttype ?? '';
            const fbCategoryId = product.fb_category_id;
            this.state = {
                fbCategoryId,
                categorySearchTerm,
                categoryOptions: [],
                fieldsToHide: variantsConfig?.map(el => el?.title?.replace(' ', '')?.toLowerCase()),
                isLoading: false,
            };
            this.handleCatIdChange = this.handleCatIdChange.bind(this);
            this.handleCatSearchTermChange = this.handleCatSearchTermChange.bind(this);
            this.getCategoryOptions = this.getCategoryOptions.bind(this);
            this.handleSearchCategoriesResponse = this.handleSearchCategoriesResponse.bind(this);
            this.handleCategorySelectionChange = this.handleCategorySelectionChange.bind(this);
            this.handleSearchButtonClick = this.handleSearchButtonClick.bind(this);
        }

        componentDidMount() {
            const { categorySearchTerm } = this.state;
            if (categorySearchTerm) {
                this.getCategoryOptions();
            }
        }

        handleCatIdChange(value) {
            product.fb_category_id = value;
            this.setState({
                fbCategoryId: value,
            });
        }

        handleCatSearchTermChange(value) {
            this.setState({
                categorySearchTerm: value,
                isLoading: !!value,
            });
            // Add timeout not to get throttled by SureDone API
            clearTimeout(this.searchCategoryTimeout);
            this.searchCategoryTimeout = setTimeout(() => {
                const { categorySearchTerm } = this.state;
                if (categorySearchTerm)
                    this.getCategoryOptions()
            }, TIMEOUT_BETWEEN_CATEGORY_SEARCHES);
        }

        handleSearchButtonClick() {
            this.getCategoryOptions();
        }

        handleSearchCategoriesResponse(response) {
            this.setState({ isLoading: false });

            if ('status' in response && response.status === 'ok') {
                const { fbCategoryId } = this.state;
                const categoryOptions = response.data?.categories ?? [];

                // If the fb category is not selected then set the category to the first recommended category
                if (!fbCategoryId && categoryOptions.length) {
                    this.setState({
                        categoryOptions,
                        fbCategoryId: categoryOptions[0]?.id
                    });
                    product.fb_category_id = categoryOptions[0]?.id;
                } else {
                    this.setState({
                        categoryOptions,
                    });
                }
            } else {
                displayAjaxError('Facebook Category Options', response);
            }
        }

        handleCategorySelectionChange(newCategoryId) {
            if (newCategoryId === 'Select a category') {
                this.handleCatIdChange('');
            } else {
                this.handleCatIdChange(newCategoryId);
            }
        }

        getCategoryOptions() {
            this.setState({ isLoading: true });

            const { categorySearchTerm } = this.state;
            const searchTerm = categorySearchTerm?.replace('&', '');
            const data = {
                'search_term': searchTerm,
                'store_index': product.fb_store_index,
            };
            $.ajax({
                url: api_url('search-categories', 'fb'),
                type: 'GET',
                data: data,
                success: this.handleSearchCategoriesResponse,
                error: function (data) {
                    this.setState({ isLoading: false });
                    displayAjaxError('Facebook Category Options', data);
                }
            });
        }

        getCategorySpecifics() {
            const { categoryOptions, fbCategoryId } = this.state;
            return categoryOptions.find(({ id }) => id == fbCategoryId)?.attributes ?? [];
        }

        render() {
            const {
                categoryOptions,
                categorySearchTerm,
                fbCategoryId,
                fieldsToHide,
                isLoading,
            } = this.state;
            return (
                <React.Fragment>
                    <div className="row">
                    <div className='form-group required col-xs-3'>
                        <label class="control-label" htmlFor='fb-category-id'>Facebook Category ID</label>
                        <input
                            required
                            className='form-control'
                            id='fb-category-id'
                            name='fb-category-id'
                            onChange={({target: {value}}) => this.handleCatIdChange(value)}
                            type='number'
                            value={fbCategoryId}
                            placeholder='Facebook Category ID'
                        />
                    </div>
                    <div className='form-group col-xs-3'>
                        <label htmlFor='category-search-term'>Search Categories</label>
                        <div className='input-group'>
                            <input
                                className='form-control'
                                id='category-search-term'
                                name='category-search-term'
                                onChange={({target: {value}}) => this.handleCatSearchTermChange(value)}
                                placeholder='Search for a category'
                                type='text'
                                value={categorySearchTerm}
                            />
                            <span className='input-group-btn'>
                                <button
                                    className='btn btn-default'
                                    type='button'
                                    onClick={() => this.handleSearchButtonClick()}
                                >
                                    <i className='fa fa-search'/>
                                </button>
                            </span>
                        </div>
                        {
                            categorySearchTerm
                            && !categoryOptions.length
                            && !isLoading
                            &&
                            <small className="form-text text-danger">
                                No categories found, please try a different/broader keyword
                            </small>
                        }
                    </div>
                    <div className='form-group col-xs-6'>
                        <label htmlFor='category-select'>Category</label>
                        <select
                            id='category-select'
                            value={fbCategoryId}
                            className='form-control'
                            placeholder='Select a category'
                            onChange={({target: {value}}) => this.handleCategorySelectionChange(value)}
                        >
                            <option key='default-option'>
                                Select a category
                            </option>
                            {
                                categoryOptions.map(category => (
                                    <option key={category.id} value={category.id}>
                                        {category.name}
                                    </option>
                                ))
                            }
                        </select>
                        <small className="form-text text-muted">
                            Select a relevant Facebook category to set the Facebook category ID
                        </small>
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
