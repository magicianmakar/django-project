/* global $, product, product:true, displayAjaxError, GoogleCategorySpecifics */
(function (variantsConfig) {
    'use strict';

    const e = React.createElement;
    const TIMEOUT_BETWEEN_CATEGORY_SEARCHES = 1000;

    class GoogleCategorySelector extends React.Component {
        searchCategoryTimeout;

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
            this.state = {
                googleCategoryId,
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

        handleCatIdChange(category_id, category_name='') {
            product.google_category_id = category_id;
            product.google_category_name = category_name;
            this.setState({
                googleCategoryId: category_id,
                googleCategoryName: category_name,
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
                const { googleCategoryId } = this.state;
                const categoryOptions = response.data?.categories ?? [];

                // If the google category is not selected then set the category to the first recommended category
                if (!googleCategoryId && categoryOptions.length) {
                    this.setState({
                        categoryOptions,
                        googleCategoryId: categoryOptions[0]?.id,
                        googleCategoryName: categoryOptions[0]?.name,
                    });
                    product.google_category_id = categoryOptions[0]?.id;
                    product.google_category_name = categoryOptions[0]?.name;
                } else {
                    this.setState({
                        categoryOptions,
                    });
                }
            } else {
                displayAjaxError('Google Category Options', response);
            }
        }

        handleCategorySelectionChange(event) {
            const newCategoryId = event.nativeEvent.target.value;
            const index = event.nativeEvent.target.selectedIndex;
            const newCategoryName = event.nativeEvent.target[index].text;
            if (newCategoryId === 'Select a category') {
                this.handleCatIdChange('', '');
            } else {
                this.handleCatIdChange(newCategoryId, newCategoryName);
            }
        }

        getCategoryOptions() {
            this.setState({ isLoading: true });
            const { categorySearchTerm } = this.state;
            const searchTerm = categorySearchTerm?.replace('&', '');
            const data = {
                'search_term': searchTerm,
                'store_index': product.google_store_index,
            };
            $.ajax({
                url: api_url('search-categories', 'google'),
                type: 'GET',
                data: data,
                success: this.handleSearchCategoriesResponse,
                error: function (data) {
                    this.setState({ isLoading: false });
                    displayAjaxError('Google Category Options', data);
                }
            });
        }

        getCategorySpecifics() {
            const { categoryOptions, googleCategoryId } = this.state;
            return categoryOptions.find(({ id }) => id == googleCategoryId)?.attributes ?? [];
        }

        render() {
            const {
                categoryOptions,
                categorySearchTerm,
                googleCategoryId,
                googleCategoryName,
                fieldsToHide,
                isLoading,
            } = this.state;
            return (
                <React.Fragment>
                    <div className="row">
                    <div className='form-group required col-xs-3'>
                        <label class="control-label" htmlFor='google-category-id'>Google Category ID</label>
                        <input
                            required
                            className='form-control'
                            id='google-category-id'
                            name='google-category-id'
                            onChange={(event) => this.handleCatIdChange(event)}
                            type='number'
                            value={googleCategoryId}
                            placeholder='Google Category ID'
                        />

                        <small className="form-text text-muted">
                            {googleCategoryName}
                        </small>

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
                            value={googleCategoryId}
                            className='form-control'
                            placeholder='Select a category'
                            onChange={(event) => this.handleCategorySelectionChange(event)}
                        >
                            <option key='default-option'>
                                Select a category
                            </option>
                            {
                                categoryOptions && categoryOptions.length !== 0 ?
                                categoryOptions.map(category => (
                                    <option key={category.id} value={category.id}>
                                        {category.name}
                                    </option>
                                )) :
                                    (
                                        googleCategoryName !== '' &&
                                        <option key={googleCategoryId} value={googleCategoryId}>
                                            {googleCategoryName}
                                        </option>
                                    )
                            }
                        </select>
                        <small className="form-text text-muted">
                            Select a relevant Google category to set the Google category ID
                        </small>
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
