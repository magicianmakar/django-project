# Production server configuration

map $uri $redirect_https {
    ~^/webhook/           0;
    ~^/marketing/feeds/   0;
    default               1;
}

upstream http_backend  {
    #server shopifytools.herokuapp.com;
    server miyazaki-35268.herokussl.com;
}

upstream https_backend  {
    server miyazaki-35268.herokussl.com:443;
}

server {

    listen 80;
    listen [::]:80;

    server_name app.shopifiedapp.com;

    server_tokens off;
    client_max_body_size 10m;

    access_log            /var/log/nginx/shopified.access.log;
    error_log            /var/log/nginx/shopified.error.log;

    #if ($redirect_https = 1) {
    #   return 301 https://$server_name$request_uri;
    #}

    location / {

        proxy_set_header Host app.shopifiedapp.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Proxy-Protocol $scheme;

        proxy_pass  http://http_backend;
    }
}

server {

    listen 443;

    server_name app.shopifiedapp.com;

    ssl_certificate           /etc/nginx/ssl/cert.crt;
    ssl_certificate_key       /etc/nginx/ssl/cert.key;

    ssl on;
    ssl_session_cache  builtin:1000  shared:SSL:10m;
    ssl_protocols  TLSv1 TLSv1.1 TLSv1.2;
    ssl_ciphers HIGH:!aNULL:!eNULL:!EXPORT:!CAMELLIA:!DES:!MD5:!PSK:!RC4;
    ssl_prefer_server_ciphers on;

    server_tokens off;
    client_max_body_size 10m;

    access_log            /var/log/nginx/shopified.access.log;
    error_log            /var/log/nginx/shopified.error.log;

    location / {

        proxy_set_header Host app.shopifiedapp.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Proxy-Protocol $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_pass  https://https_backend;
    }
}
