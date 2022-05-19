/* global $, product, product:true, displayAjaxError, EbayCategorySpecifics */
(function (variantsConfig) {
    'use strict';

    const e = React.createElement;
    const TIMEOUT_BETWEEN_CATEGORY_SEARCHES = 1000;

    class EbayCategorySelector extends React.Component {
        searchCategoryTimeout;
        getCategorySpecificsTimeout;

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
            this.handleCatIdChange = this.handleCatIdChange.bind(this);
            this.handleCatSearchTermChange = this.handleCatSearchTermChange.bind(this);
            this.getCategoryOptions = this.getCategoryOptions.bind(this);
            this.handleSearchCategoriesResponse = this.handleSearchCategoriesResponse.bind(this);
            this.handleCategorySelectionChange = this.handleCategorySelectionChange.bind(this);
            this.handleSearchButtonClick = this.handleSearchButtonClick.bind(this);
            this.handleGetCategorySpecificsResponse = this.handleGetCategorySpecificsResponse.bind(this);
        }

        componentDidMount() {
            const { categorySearchTerm, ebayCategoryId } = this.state;
            if (categorySearchTerm) {
                this.getCategoryOptions();
            }
            if (ebayCategoryId) {
                this.getCategorySpecifics();
            }
        }

        handleCatIdChange(value) {
            product.ebay_category_id = value;
            this.setState({
                ebayCategoryId: value,
            });

            clearTimeout(this.getCategorySpecificsTimeout);
            this.getCategorySpecificsTimeout = setTimeout(() => {
                const { ebayCategoryId } = this.state;
                if (ebayCategoryId) {
                    this.getCategorySpecifics();
                }
            }, TIMEOUT_BETWEEN_CATEGORY_SEARCHES)
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
                const { ebayCategoryId } = this.state;
                const categoryOptions = response.data.categories ? Object.values(response.data.categories) : [];

                // If the ebay category is not selected then set the category to the first recommended category
                if (!ebayCategoryId && categoryOptions.length) {
                    this.setState({
                        categoryOptions,
                        ebayCategoryId: categoryOptions[0]?.id
                    });
                    product.ebay_category_id = categoryOptions[0]?.id;
                    this.getCategorySpecifics();
                } else {
                    this.setState({
                        categoryOptions,
                    });
                }
            } else {
                displayAjaxError('eBay Category Options', response);
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
                'store_index': product.ebay_store_index,
            };
            $.ajax({
                url: api_url('search-categories', 'ebay'),
                type: 'GET',
                data: data,
                success: this.handleSearchCategoriesResponse,
                error: function (data) {
                    this.setState({ isLoading: false });
                    displayAjaxError('eBay Category Options', data);
                }
            });
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
                categoryOptions,
                categorySearchTerm,
                categorySpecifics,
                ebayCategoryId,
                fieldsToHide,
                isLoading,
            } = this.state;
            return (
                <React.Fragment>
                    <div className="row">
                    <div className='form-group required col-xs-3'>
                        <label class="control-label" htmlFor='ebay-category-id'>eBay Category ID</label>
                        <input
                            required
                            className='form-control'
                            id='ebay-category-id'
                            name='ebay-category-id'
                            onChange={({target: {value}}) => this.handleCatIdChange(value)}
                            type='number'
                            value={ebayCategoryId}
                            placeholder='eBay Category ID'
                        />
                        {
                            categorySpecifics
                            && 'display_name' in categorySpecifics
                            && 'id' in categorySpecifics
                            && categorySpecifics.id == ebayCategoryId
                            && (
                                <small className="form-text text-muted">
                                    {categorySpecifics.display_name}
                                </small>
                            )
                        }
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
                            value={ebayCategoryId}
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
                            Search and select a relevant eBay category to set the eBay category ID
                        </small>
                    </div>
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
