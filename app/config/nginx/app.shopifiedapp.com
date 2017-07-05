
map $uri $dropified_redirects {
    ~^/webhook/           0;
    ~^/marketing/feeds/   0;
    ~^/api/               0;

    default               1;
}

upstream shopifiedapp_backend  {
    server shopifytools.herokuapp.com;
}

upstream shopifiedhelper_backend  {
  server shopified-helper-app.herokuapp.com;
}

server {
    listen 80;
    listen [::]:80;

    listen 443 ssl http2;
    listen [::]:443 ssl http2;

    server_name app.shopifiedapp.com;

    client_body_timeout 5s;
    client_header_timeout 5s;

    ssl_prefer_server_ciphers on;
    ssl_protocols TLSv1 TLSv1.1 TLSv1.2;
    ssl_ciphers EECDH+CHACHA20:EECDH+AES128:RSA+AES128:EECDH+AES256:RSA+AES256:EECDH+3DES:RSA+3DES:!MD5;
    ssl_certificate           /etc/nginx/ssl/cert.crt;
    ssl_certificate_key       /etc/nginx/ssl/cert.key;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    server_tokens off;
    client_max_body_size 10m;

    access_log            /var/log/nginx/shopified.access.log;
    error_log            /var/log/nginx/shopified.error.log;

    location ~ ^/(robots\.txt|favicon\.png|favicon\.ico|crossdomain\.xml) {
        root /usr/share/nginx/app.shopifiedapp.com;

        access_log off;
        error_log off;

        try_files $uri $uri/ =404;
    }

    #location /webhook/shopify/ {
    #    return 500;
    #}

    #location /webhook/shopify/orders-update {
    #    return 500;
    #}

    #location /webhook/shopify/products-update {
    #  return 200;
    #}

    #location /webhook/shopify/products-delete {
    #  return 200;
    #}

    #deny 93.95.82.12;

    location /api/ali/ {
        access_log  /var/log/nginx/helperapp.access.log;
        error_log   /var/log/nginx/helperapp.error.log;

        proxy_set_header Host shopified-helper-app.herokuapp.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Proxy-Protocol $scheme;

        proxy_pass  http://shopifiedhelper_backend;
    }

    if ($dropified_redirects = 1) {
       return 302 https://app.dropified.com$request_uri;
    }

    location / {
        rewrite /terms-of-service /pages/terms-of-service  break;

        proxy_set_header Host $server_name;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Proxy-Protocol $scheme;

        proxy_pass  http://shopifiedapp_backend;
    }
}
