#/bin/bash

find -iname '*.js' \
    -not -iregex '.+node_modules.+' \
    -not -iregex '.+bower_components.+' \
    -not -iregex '.+venv.+' \
    -not -iregex '.+libs.+' \
    -not -iregex '.+htmlcov.+' \
    -not -iregex '.+plugins.+' \
    -not -iregex '.+.min.js' \
    -not -iname 'shopify_carrier.js' \
    -not -iname 'bootstrap.js' \
    -not -iname 'daterangepicker.js' \
    -not -iname 'inspinia.js' \
    -not -iname 'jquery.unveil.js' \
    -not -iname 'trix.js' \
    -not -iname 'baremetrics.js' \
    -not -iname 'clippingmagic.js'  | xargs jshint --reporter=node_modules/jshint-stylish/index.js
