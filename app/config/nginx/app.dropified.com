# Configuration for production server

proxy_cache_path /tmp/nginx-cache levels=1:2 keys_zone=cache_ext_config:10m max_size=1g inactive=150m use_temp_path=off;

limit_req_zone $binary_remote_addr zone=iplimit:10m rate=1r/s;
limit_req_zone $uri zone=urilimit:10m rate=10r/s;
limit_req_zone $request_uri zone=requrilimit:100m rate=6r/s;

server {
    listen 80;
    listen [::]:80;

    listen 443 ssl;
    listen [::]:443 ssl;

    server_name app.dropified.com;

    ### Hide OS and Nginx version
    server_tokens off;

    ### Client request limits
    client_body_timeout 5s;
    client_header_buffer_size 4K;
    client_header_timeout 5s;
    client_max_body_size 10m;
    #proxy_buffer_size 4096k;
    #proxy_buffers 5 4096k;

    ### SSL Settings
    ssl_certificate     /etc/nginx/ssl/app.dropified.com/app_dropified_com-bundle.crt;
    ssl_certificate_key /etc/nginx/ssl/app.dropified.com/app_dropified_com.key;
    ssl_ciphers EECDH+CHACHA20:EECDH+AES128:RSA+AES128:EECDH+AES256:RSA+AES256:EECDH+3DES:RSA+3DES:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_protocols TLSv1 TLSv1.1 TLSv1.2;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    ### Default log files
    access_log  /var/log/nginx/dropified.access.log;
    error_log   /var/log/nginx/dropified.error.log;

    ### Default Proxy Settings
    proxy_set_header Host $server_name;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Proxy-Protocol $scheme;

    ### Syncing and Alerts
    #location /api/all/orders-sync { return 500; }
    #location /webhook/price-monitor/product { return 200; }

    ### Shopify Webhooks
    location /webhook/shopify/products-update { return 200; }
    #location /webhook/shopify/ { return 500; }
    #location /webhook/shopify/orders-update { return 500; }
    #location /webhook/shopify/products-delete { return 200; }

    ### ClickFunnels server check
    location /funnel_webhooks/test { return 200; }

    ### Problematic feeds
    location /marketing/feeds/woo/028aa634/2 { return 404; }
    location /marketing/feeds/woo/f1aa8a34/2 { return 404; }

    ### Static files
    location ~ ^/(robots\.txt|favicon\.png|favicon\.ico|crossdomain\.xml) {
        root /usr/share/nginx/app.dropified.com;

        access_log off;
        error_log off;

        try_files $uri $uri/ =404;
    }

    ### Automated Captcha Solver Proxy
    location /api/ali/solve {
        access_log  /var/log/nginx/captcha.log;
        error_log   /var/log/nginx/captcha.error;

        proxy_set_header Host dropified-captcha.herokuapp.com;
        proxy_pass  http://dropified-captcha.herokuapp.com;
    }

    ### Dropified Helper App Proxy
    location /api/ali/ {
        access_log  /var/log/nginx/helperapp.access.log;
        error_log   /var/log/nginx/helperapp.error.log;

        proxy_set_header Host shopified-helper-app.herokuapp.com;
        proxy_pass  http://shopified-helper-app.herokuapp.com;
    }

    ### Aliextractor App Proxy
    location /api/ae/ {
        access_log  /var/log/nginx/aliextractor.access.log;
        error_log   /var/log/nginx/aliextractor.error.log;

        proxy_set_header Host api.aliextractor.com;
        proxy_pass  http://api.aliextractor.com/;
    }

    ### Extension Settings API
    location /api/extension-settings {
        proxy_cache cache_ext_config;
        proxy_cache_key "$host$request_uri$cookie_user";
        proxy_cache_valid 150m;
        #add_header X-Cached $upstream_cache_status;

        proxy_pass  http://shopifytools.herokuapp.com;
    }

    ### Request limit
    location /webhook/shopify/orders-update {
        limit_req zone=requrilimit burst=20 nodelay;

        proxy_pass  http://shopifytools.herokuapp.com;
    }

    location /api/shopify/import-product {
        limit_req zone=iplimit;

        proxy_pass  http://shopifytools.herokuapp.com;
    }

    ### Dropified App Proxy
    location / {
        rewrite /pages/terms-of-service https://www.dropified.com/terms-of-service/ redirect;
        rewrite /terms-of-service https://www.dropified.com/terms-of-service/ redirect;

        rewrite /pages/view/what-websites-will-dropified-import-products-from /pages/source-import-products redirect;
        rewrite /pages/view/what-websites-will-shopified-app-import-products-from /pages/source-import-products redirect;
        rewrite /pages/what-websites-will-dropified-import-products-from /pages/source-import-products redirect;
        rewrite /pages/what-websites-will-shopified-app-import-products-from /pages/source-import-products redirect;
        rewrite /pages/content/source-full-automation /pages/source-import-products redirect;
        rewrite /pages/content/source-one_click_support /pages/source-import-products redirect;

        proxy_pass  http://shopifytools.herokuapp.com;
    }
}
