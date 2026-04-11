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

# Check if we have a valid cert already
if certbot certificates 2>/dev/null | grep -q "Certificate Name: $DOMAIN"; then
    certbot renew --no-self-upgrade --cert-name "$DOMAIN" --post-hook "systemctl reload nginx" || true
else
    # Clean any failed attempts
    rm -rf /etc/letsencrypt/live/$DOMAIN
    rm -rf /etc/letsencrypt/archive/$DOMAIN
    rm -rf /etc/letsencrypt/renewal/$DOMAIN.conf

    certbot --nginx -d "$DOMAIN" \
        --non-interactive --agree-tos --email "$EMAIL" \
        --redirect || echo "Certbot failed — will retry on next deploy."
fi

exit 0
