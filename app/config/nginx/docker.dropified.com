# Configuration for Development server in Docker

events { }

http {
    upstream dropified_backend  {
        server web:8000;
    }

    upstream dropifiedhelper_backend  {
        server shopified-helper-app.herokuapp.com;
    }

    upstream captchasolver_backend  {
        server dropified-captcha.herokuapp.com;
    }

    upstream aliextractor_backend  {
        server api.aliextractor.com;
    }

    server {
        listen 80;
        listen [::]:80;

        server_name dev.dropified.com;

        ### Hide OS and Nginx version
        server_tokens off;

        ### Client request limits
        client_body_timeout 5s;
        client_header_buffer_size 4K;
        client_header_timeout 5s;
        client_max_body_size 10m;

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
            proxy_pass  http://captchasolver_backend;
        }

        ### Dropified Helper App Proxy
        location /api/ali/ {
            access_log  /var/log/nginx/helperapp.access.log;
            error_log   /var/log/nginx/helperapp.error.log;

            proxy_set_header Host shopified-helper-app.herokuapp.com;
            proxy_pass  http://dropifiedhelper_backend;
        }

        ### Aliextractor App Proxy
        location /api/ae/ {
            access_log  /var/log/nginx/aliextractor.access.log;
            error_log   /var/log/nginx/aliextractor.error.log;

            proxy_set_header Host api.aliextractor.com;
            proxy_pass  http://aliextractor_backend/;
        }

        ### Dropified App Proxy
        location / {
            rewrite /terms-of-service /pages/17 break;
            rewrite /pages/view/what-websites-will-shopified-app-import-products-from /pages/11 break;
            rewrite /pages/what-websites-will-shopified-app-import-products-from /pages/11 break;

            proxy_pass  http://dropified_backend;
        }
    }
}
