#!/bin/bash
set +e

DOMAIN="ctrlaltjay.dev"
EMAIL="rone_peh@hotmail.com"

# Install certbot if not present
if ! command -v certbot &> /dev/null; then
    python3 -m venv /opt/certbot
    /opt/certbot/bin/pip install --upgrade pip
    /opt/certbot/bin/pip install certbot certbot-nginx
    ln -sf /opt/certbot/bin/certbot /usr/local/bin/certbot
fi

# Get cert (certonly — don't modify nginx, we manage config ourselves)
if certbot certificates 2>/dev/null | grep -q "Certificate Name: $DOMAIN"; then
    certbot renew --no-self-upgrade --cert-name "$DOMAIN" || true
else
    # Clean any failed attempts
    rm -rf /etc/letsencrypt/live/$DOMAIN
    rm -rf /etc/letsencrypt/archive/$DOMAIN
    rm -rf /etc/letsencrypt/renewal/$DOMAIN.conf

    certbot certonly --nginx -d "$DOMAIN" \
        --non-interactive --agree-tos --email "$EMAIL" \
        || echo "Certbot failed — will retry on next deploy."
fi

# Write HTTPS server block if cert exists
if [ -f /etc/letsencrypt/live/$DOMAIN/fullchain.pem ]; then
    cat > /etc/nginx/conf.d/https.conf <<'NGINX'
server {
    listen 443 ssl;
    server_name ctrlaltjay.dev;

    ssl_certificate     /etc/letsencrypt/live/ctrlaltjay.dev/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ctrlaltjay.dev/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    location / {
        proxy_pass          http://127.0.0.1:8000;
        proxy_set_header    Host $host;
        proxy_set_header    X-Real-IP $remote_addr;
        proxy_set_header    X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header    X-Forwarded-Proto https;
    }
}
NGINX

    systemctl reload nginx || systemctl restart nginx || true
fi

exit 0
