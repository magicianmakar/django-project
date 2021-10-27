/* global $, config, toastr, swal, product, product:true, displayAjaxError, React */
/*jshint esversion: 11 */
/**
 *
 * @param specificsData https://www.suredone.com/guides/api/#/reference/taxonomy-specifics-api-requests
 * @returns {JSX.Element}
 * @constructor
 */
function EbayCategorySpecifics(props) {
    'use strict';
    const [productSpecifics, setProductSpecifics] = React.useState(product);

    const handleCustomFieldChange = (productFieldKey, value, fieldDetails) => {
        product[productFieldKey] = value;
        product[getEbaySpecificsKey(productFieldKey)] = value;
        setProductSpecifics({
            ...product,
        });
    };

    const getEbaySpecificsKey = (fieldName) => {
        return `ebayitemspecifics${fieldName}`;
    };

    const getProductKey = (fieldName, fieldDetails) => {
        let productKey = fieldName;
        // TODO: sync with the SureDone support on match rules
        // if ('match' in fieldDetails && fieldDetails.match !== 'both') {
        //     productKey = `ebay${product.ebay_store_index}itemspecifics${fieldName}`;
        // }
        return productKey;
    };

    const deriveProductKeysFromSpecifics = (data) => {
        const allData = [];
        let product_key = '';
        let ebay_specifics_key = '';
        if (typeof data === 'object' && data !== null) {
            Object.keys(data).forEach(key => {
                const specificsDetails = data[key];
                if (specificsDetails) {
                    product_key = getProductKey(key, specificsDetails);
                    ebay_specifics_key = getEbaySpecificsKey(key);
                    allData.push(product_key);
                    allData.push(ebay_specifics_key);
                }
            });
        }
        return allData;
    };

    const getAllEbaySpecificsKeys = () => {
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
            const allKeys = getAllEbaySpecificsKeys();
            const parsedData = JSON.parse(product.data);

            // For use when saving a product
            product['extendedFieldsList'] = allKeys;

            allKeys.forEach(key => {
                // Check if the key is not defined in the top level product details
                if (!(key in product) && key in parsedData) {
                    product[key] = parsedData[key] ?? '';
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
                key={`ebay-specifics-field-${key}`}
            >
                <label class="control-label" htmlFor={`ebay-specifics-field-${key}`}>
                    {'name' in specificsDetails ? specificsDetails.name : key}
                </label>
                <input
                    {...additionalFields}
                    className='form-control'
                    id={`ebay-specifics-field-${key}`}
                    list={`ebay-specifics-suggestions-${key}`}
                    name={`ebay-specifics-field-${key}`}
                    onChange={({target: {value}}) => handleCustomFieldChange(productKey, value, specificsDetails)}
                    placeholder={'name' in specificsDetails ? specificsDetails.name : key}
                    type='text'
                    value={getFieldValue(productKey)}
                />
                <datalist
                    id={`ebay-specifics-suggestions-${key}`}
                >
                {
                    values.map(value => (
                        <option
                            className={`ebay-specifics-suggestion-option-${key}`}
                            key={`ebay-specifics-suggestion-option-${key}`}
                            value={value}
                        />
                    ))
                }
                </datalist>
            </div>
        )
    }
    if (props?.specifics?.required || props?.specifics?.recommended)
        return (
            <div style={{ paddingLeft: 15, paddingRight: 15 }}>
                <h3>eBay Item Specifics</h3>
                <div className="panel-group" id="ebay-specifics-fields-accordion">
                    {
                        props?.specifics?.required &&
                            <div className="panel panel-default">
                                <div className="panel-heading">
                                    <h4 className="panel-title">
                                        <a data-toggle="collapse" href="#ebay-specifics-required-fields">Required Fields</a>
                                    </h4>
                                </div>
                                <div id="ebay-specifics-required-fields" className="panel-collapse collapse in">
                                    <div className="panel-body">
                                        {
                                            Object.keys(props.specifics.required).filter(specificsKey => (
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
                    }

                    {
                        props?.specifics?.recommended &&
                            <div className="panel panel-default">
                                <div className="panel-heading">
                                    <h4 className="panel-title">
                                        <a data-toggle="collapse" href="#ebay-specifics-recommended-fields">Recommended Fields</a>
                                    </h4>
                                </div>
                                <div id="ebay-specifics-recommended-fields" className="panel-collapse collapse">
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
                                    </div>
                                </div>
                            </div>
                    }
                </div>
            </div>
        );
    else return null;
}
