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

# Get or renew certificate
if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
    certbot --nginx -d "$DOMAIN" \
        --non-interactive --agree-tos --email "$EMAIL" \
        --redirect || echo "Certbot failed — will retry on next deploy."
else
    certbot renew --no-self-upgrade --cert-name "$DOMAIN" --post-hook "systemctl reload nginx" || true
fi

exit 0
