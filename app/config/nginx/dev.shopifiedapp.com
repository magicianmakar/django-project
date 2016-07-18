# Configuration for development server

map $uri $redirect_https {
    ~^/webhook/           0;
    ~^/marketing/feeds/   0;
    default               1;
}

upstream http_backend  {
  server 127.0.0.1:8000;
}

upstream https_backend  {
  server 127.0.0.1:8000;
}

upstream ali_node  {
  server 127.0.0.1:9000;
}

server {
    listen 80;
    listen [::]:80;

    server_name dev.shopifiedapp.com;

    server_tokens off;
    client_max_body_size 10m;

    access_log            /var/log/nginx/shopified.access.log;
    error_log            /var/log/nginx/shopified.error.log;

    #if ($redirect_https = 1) {
    #   return 301 https://$server_name$request_uri;
    #}

    location ~ ^/(robots\.txt|favicon\.png|favicon\.ico|crossdomain\.xml) {
        root /usr/share/nginx/app.shopifiedapp.com;

        access_log off;
        error_log off;

        try_files $uri $uri/ =404;
    }

    location /api/ali {
        access_log  /var/log/nginx/helperapp.access.log;
        error_log   /var/log/nginx/helperapp.error.log;

        proxy_set_header Host dev.shopifiedapp.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Proxy-Protocol $scheme;

        proxy_pass  http://ali_node;
    }

    location / {
        proxy_set_header Host dev.shopifiedapp.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Proxy-Protocol $scheme;

        proxy_pass  http://http_backend;
    }
}

server {
    listen 443;

    server_name dev.shopifiedapp.com;

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

    location ~ ^/(robots\.txt|favicon\.png|favicon\.ico|crossdomain\.xml) {
        root /usr/share/nginx/app.shopifiedapp.com;

        access_log off;
        error_log off;

        try_files $uri $uri/ =404;
    }

    location /api/ali {
        access_log  /var/log/nginx/helperapp.access.log;
        error_log   /var/log/nginx/helperapp.error.log;

        proxy_set_header Host dev.shopifiedapp.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Proxy-Protocol $scheme;

        proxy_pass  http://ali_node;
    }
    
    location / {
        proxy_set_header Host dev.shopifiedapp.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Proxy-Protocol $scheme;

        proxy_pass  http://https_backend;
    }
}
