# Guide: Reverse Proxy with Nginx

Nginx is commonly used for ingress policy, TLS termination, and routing before Palfrey.

## Reference app

```python
{!> ../../../docs_src/guides/nginx_reverse_proxy_app.py !}
```

## Minimal HTTP proxy config

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

## WebSocket upgrade forwarding

If your app uses websocket endpoints, ensure upgrade headers are forwarded:

```nginx
location /ws {
    proxy_pass http://palfrey_upstream;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## Palfrey trust configuration

```bash
palfrey main:app --proxy-headers --forwarded-allow-ips 127.0.0.1
```

Use explicit proxy IP ranges in real deployments.

## Verification checklist

- request scheme seen by app is correct (`http` vs `https`)
- client IP seen by app is expected
- websocket upgrade requests succeed end-to-end

## Non-technical summary

Nginx is your front door.
Palfrey is the application runtime behind that door.
Correct trust settings are what keep address/scheme data reliable.
