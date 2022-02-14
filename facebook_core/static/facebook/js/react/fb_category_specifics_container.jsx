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
function FBCategorySpecifics(props) {
    'use strict';
    const [productSpecifics, setProductSpecifics] = React.useState(product);

    const handleCustomFieldChange = (productFieldKey, value, fieldDetails) => {
        product[productFieldKey] = product[getFBSpecificsKey(productFieldKey)] = value;
        setProductSpecifics({
            ...product,
        });
    };

    const getFBSpecificsKey = (fieldName) => {
        return `${fieldName}`;
    };

    const formatFBPrefix = (instanceId) => (
        instanceId === '1' || instanceId === 1 ? 'facebook' : `facebook${instanceId}`
    );

    const getProductKey = (fieldName, fieldDetails) => {
        return fieldName;
    };

    const deriveProductKeysFromSpecifics = (data) => {
        const allData = [];
        let product_key = '';
        let fb_specifics_key = '';
        if (typeof data === 'object' && data !== null) {
            Object.keys(data).forEach(key => {
                const specificsDetails = data[key];
                if (specificsDetails) {
                    product_key = getProductKey(key, specificsDetails);
                    fb_specifics_key = getFBSpecificsKey(key);
                    allData.push(product_key);
                    allData.push(fb_specifics_key);
                }
            });
        }
        return allData;
    };

    const getAllFBSpecificsKeys = () => {
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
            const allKeys = getAllFBSpecificsKeys();
            const parsedData = JSON.parse(product.data);

            // Try extracting values from fb item specifics for the category specific fields
            try {
                const fbKey = `${formatFBPrefix(parsedData.dropifiedconnectedstoreid)}options`;
                const fbOptions = JSON.parse(parsedData[fbKey]);
                const itemSpecifics = fbOptions.itemspecifics;
                Object.keys(itemSpecifics).forEach(key => {
                    product[key] = product[getFBSpecificsKey(key)] = itemSpecifics[key];
                });
            } catch (e) {
            }

            // For use when saving a product
            product['extendedFieldsList'] = allKeys;

            allKeys.forEach(key => {
                // Check if the key is not defined in the top level product details
                if (!(key in product) && key in parsedData) {
                    product[key] = product[getFBSpecificsKey(key)] = parsedData[key] ?? '';
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
                key={`fb-specifics-field-${key}`}
            >
                <label class="control-label" htmlFor={`fb-specifics-field-${key}`}>
                    {'name' in specificsDetails ? specificsDetails.name : key}
                </label>
                <input
                    {...additionalFields}
                    className='form-control'
                    id={`fb-specifics-field-${key}`}
                    list={`fb-specifics-suggestions-${key}`}
                    name={`fb-specifics-field-${key}`}
                    onChange={({target: {value}}) => handleCustomFieldChange(productKey, value, specificsDetails)}
                    placeholder={'name' in specificsDetails ? specificsDetails.name : key}
                    type='text'
                    value={getFieldValue(productKey)}
                />
                <datalist
                    id={`fb-specifics-suggestions-${key}`}
                >
                {
                    values.map(value => (
                        <option
                            className={`fb-specifics-suggestion-option-${key}`}
                            key={`fb-specifics-suggestion-option-${key}`}
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
            <h3>Facebook Item Specifics</h3>
            <div className="panel-group" id="fb-specifics-fields-accordion">
                <div className="panel panel-default">
                    <div className="panel-heading">
                        <h4 className="panel-title">
                            <a data-toggle="collapse" href="#fb-specifics-required-fields">Required Fields</a>
                        </h4>
                    </div>
                    <div id="fb-specifics-required-fields" className="panel-collapse collapse in">
                        <div className="panel-body">
                            <div
                                className='form-group col-xs-3 required'
                                key='fb-specifics-field-product-link'
                            >
                                <label className="control-label" htmlFor='fb-specifics-field-product-link'>
                                    Product Page Link
                                </label>
                                <input
                                    required
                                    className='form-control'
                                    id='fb-specifics-field-product-link'
                                    name='fb-specifics-field-product-link'
                                    onChange={({target: {value}}) => handleCustomFieldChange('page_link', value)}
                                    placeholder='Product Page Link'
                                    type='text'
                                    value={getFieldValue('page_link')}
                                />
                            </div>

                            <div
                                className='form-group col-xs-3 required'
                                key='fb-specifics-field-brand'
                            >
                                <label className="control-label" htmlFor='fb-specifics-field-brand'>
                                    Brand
                                </label>
                                <input
                                    required
                                    className='form-control'
                                    id='fb-specifics-field-brand'
                                    name='fb-specifics-field-brand'
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
                                    <a data-toggle="collapse" href="#fb-specifics-recommended-fields">Recommended Fields</a>
                                </h4>
                            </div>
                            <div id="fb-specifics-recommended-fields" className="panel-collapse collapse">
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
