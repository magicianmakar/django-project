/* global $, config, toastr, swal, product, product:true, displayAjaxError, React */
/*jshint esversion: 11 */
/**
 *
 * @param props
 *  specifics: Array<Object>
 *  fieldsToHide: Array<string>
 * @returns {JSX.Element}
 * @constructor
 */
function GoogleCategorySpecifics(props) {
    'use strict';
    const [productSpecifics, setProductSpecifics] = React.useState(product);

    const handleCustomFieldChange = (productFieldKey, value, fieldDetails) => {
        product[productFieldKey] = product[getGoogleSpecificsKey(productFieldKey)] = value;
        setProductSpecifics({
            ...product,
        });
    };

    const getGoogleSpecificsKey = (fieldName) => {
        return `${fieldName}`;
    };

    const formatGooglePrefix = (instanceId) => (
        instanceId === '1' || instanceId === 1 ? 'google' : `google${instanceId}`
    );

    const getProductKey = (fieldName, fieldDetails) => {
        return fieldName;
    };

    const deriveProductKeysFromSpecifics = (data) => {
        const allData = [];
        let product_key = '';
        let google_specifics_key = '';
        if (typeof data === 'object' && data !== null) {
            Object.keys(data).forEach(key => {
                const specificsDetails = data[key];
                if (specificsDetails) {
                    product_key = getProductKey(key, specificsDetails);
                    google_specifics_key = getGoogleSpecificsKey(key);
                    allData.push(product_key);
                    allData.push(google_specifics_key);
                }
            });
        }
        return allData;
    };

    const getAllGoogleSpecificsKeys = () => {
        return [
            ...deriveProductKeysFromSpecifics(props?.specifics?.required),
            ...deriveProductKeysFromSpecifics(props?.specifics?.recommended),
        ];
    };

    const getFieldValue = (productKey) => {
        return productKey in productSpecifics ? productSpecifics[productKey] : '';
    };

    React.useEffect(() => {
        try {
            const allKeys = getAllGoogleSpecificsKeys();
            const parsedData = JSON.parse(product.data);

            // Try extracting values from google item specifics for the category specific fields
            try {
                const googleKey = `${formatGooglePrefix(parsedData.dropifiedconnectedstoreid)}options`;
                const googleOptions = JSON.parse(parsedData[googleKey]);
                const itemSpecifics = googleOptions.itemspecifics;
                Object.keys(itemSpecifics).forEach(key => {
                    product[key] = product[getGoogleSpecificsKey(key)] = itemSpecifics[key];
                });
            } catch (e) {
            }

            // For use when saving a product
            product['extendedFieldsList'] = allKeys;

            allKeys.forEach(key => {
                // Check if the key is not defined in the top level product details
                if (!(key in product) && key in parsedData) {
                    product[key] = product[getGoogleSpecificsKey(key)] = parsedData[key] ?? '';
                    setProductSpecifics({ ...product });
                }
            });

        } catch (e) {
        }

    }, [props.specifics]);

    /**
     * Render a single custom field
     * @param {string} key
     * @param {Object} specificsDetails
     * @param {boolean} required
     * @returns {JSX.Element}
     */
    const renderCustomField = (key, specificsDetails, required) => {
        const productKey = getProductKey(key, specificsDetails);
        const additionalFields = required ? {required: true} : {};
        const values = Object.values(specificsDetails?.values ?? {});
        return (
            <div
                {...additionalFields}
                className={`form-group col-xs-3 ${required ? 'required' : ''}`}
                key={`google-specifics-field-${key}`}
            >
                <label class="control-label" htmlFor={`google-specifics-field-${key}`}>
                    {'name' in specificsDetails ? specificsDetails.name : key}
                </label>
                <input
                    {...additionalFields}
                    className='form-control'
                    id={`google-specifics-field-${key}`}
                    list={`google-specifics-suggestions-${key}`}
                    name={`google-specifics-field-${key}`}
                    onChange={({target: {value}}) => handleCustomFieldChange(productKey, value, specificsDetails)}
                    placeholder={'name' in specificsDetails ? specificsDetails.name : key}
                    type='text'
                    value={getFieldValue(productKey)}
                />
                <datalist
                    id={`google-specifics-suggestions-${key}`}
                >
                {
                    values.map(value => (
                        <option
                            className={`google-specifics-suggestion-option-${key}`}
                            key={`google-specifics-suggestion-option-${key}`}
                            value={value}
                        />
                    ))
                }
                </datalist>
            </div>
        )
    }
    return (
        <div style={{ paddingLeft: 15, paddingRight: 15 }}>
            <h3>Google Item Specifics</h3>
            <div className="panel-group" id="google-specifics-fields-accordion">
                <div className="panel panel-default">
                    <div className="panel-heading">
                        <h4 className="panel-title">
                            <a data-toggle="collapse" href="#google-specifics-required-fields">Required Fields</a>
                        </h4>
                    </div>
                    <div id="google-specifics-required-fields" className="panel-collapse collapse in">
                        <div className="panel-body">
                            <div
                                className='form-group col-xs-3 required'
                                key='google-specifics-field-product-link'
                            >
                                <label className="control-label" htmlFor='google-specifics-field-product-link'>
                                    Product Page Link
                                </label>
                                <input

                                    className='form-control'
                                    id='google-specifics-field-product-link'
                                    name='google-specifics-field-product-link'
                                    onChange={({target: {value}}) => handleCustomFieldChange('page_link', value)}
                                    placeholder='Product Page Link'
                                    type='text'
                                    value={getFieldValue('page_link')}
                                />
                            </div>

                            <div
                                className='form-group col-xs-3 required'
                                key='google-specifics-field-brand'
                            >
                                <label className="control-label" htmlFor='google-specifics-field-brand'>
                                    Brand
                                </label>
                                <input
                                    required
                                    className='form-control'
                                    id='google-specifics-field-brand'
                                    name='google-specifics-field-brand'
                                    onChange={({target: {value}}) => handleCustomFieldChange('brand', value)}
                                    placeholder='Brand'
                                    type='text'
                                    value={getFieldValue('brand')}
                                />
                            </div>

                            {
                                props?.specifics?.required && Object.keys(props.specifics.required).filter(specificsKey => (
                                    !props.fieldsToHide.includes(specificsKey))
                                ).map(specificsKey => {
                                    const specificsDetails = props?.specifics?.required?.[specificsKey];
                                    if (specificsDetails)
                                        return renderCustomField(specificsKey, specificsDetails, true);
                                    else return null;
                                })
                            }
                        </div>
                    </div>
                </div>

                {
                    props?.specifics?.recommended &&
                        <div className="panel panel-default">
                            <div className="panel-heading">
                                <h4 className="panel-title">
                                    <a data-toggle="collapse" href="#google-specifics-recommended-fields">Recommended Fields</a>
                                </h4>
                            </div>
                            <div id="google-specifics-recommended-fields" className="panel-collapse collapse">
                                <div className="panel-body">
                                    {
                                        Object.keys(props.specifics.recommended).filter(specificsKey => (
                                            !props.fieldsToHide.includes(specificsKey))
                                        ).map(specificsKey => {
                                            const specificsDetails = props?.specifics?.recommended?.[specificsKey];
                                            if (specificsDetails)
                                                return renderCustomField(specificsKey, specificsDetails, false);
                                            else return null;
                                        })
                                    }
                                    {
                                        !Object.keys(props.specifics.recommended).length &&
                                            <div>
                                                <p>No recommended fields</p>
                                            </div>
                                    }
                                </div>
                            </div>
                        </div>
                }
            </div>
        </div>
    );
}
