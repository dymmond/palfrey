# Guide: Reverse Proxy with Nginx

Use a reverse proxy when you need edge controls, TLS termination, rate limiting, and unified ingress management.

## App used in this guide

```python
{!> ../../../docs_src/guides/nginx_reverse_proxy_app.py !}
```

## Minimal Nginx upstream shape

```nginx
upstream palfrey_upstream {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    location / {
        proxy_pass http://palfrey_upstream;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
```

## Palfrey startup for trusted proxy headers

```bash
palfrey myapp.main:app --proxy-headers --forwarded-allow-ips 127.0.0.1
```

For containerized internal networks, set trusted ranges explicitly.

## Validation steps

1. Send request through Nginx.
2. Confirm app sees expected `scheme` and client IP behavior.
3. Confirm direct untrusted requests do not bypass trust boundaries.

## Non-Technical explanation

Nginx is the building entrance.
Palfrey is the application floor behind it.
The proxy decides who gets in and what metadata gets forwarded.
