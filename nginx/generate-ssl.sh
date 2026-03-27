#!/bin/sh
set -e

CERT_DIR=/etc/nginx/certs
ACME_ROOT=/var/www/certbot
mkdir -p "$CERT_DIR" "$ACME_ROOT"

_log() { echo "[ssl] $*"; }

_write_selfsigned() {
    local CN="$1"
    local IP="${2:-127.0.0.1}"
    _log "Generating self-signed certificate for CN=$CN IP=$IP ..."
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "$CERT_DIR/privkey.pem" \
        -out   "$CERT_DIR/fullchain.pem" \
        -subj  "/C=IN/ST=India/L=City/O=ChainBreak/CN=$CN" \
        -addext "subjectAltName=DNS:$CN,DNS:localhost,IP:$IP,IP:127.0.0.1"
    cp "$CERT_DIR/fullchain.pem" "$CERT_DIR/chain.pem"
    chmod 600 "$CERT_DIR/privkey.pem"
    chmod 644 "$CERT_DIR/fullchain.pem" "$CERT_DIR/chain.pem"
    _log "Self-signed certificate written to $CERT_DIR"
}

_ensure_dhparam() {
    if [ ! -f "$CERT_DIR/dhparam.pem" ]; then
        if [ -f /etc/nginx/certs-default/dhparam.pem ]; then
            cp /etc/nginx/certs-default/dhparam.pem "$CERT_DIR/dhparam.pem"
            chmod 644 "$CERT_DIR/dhparam.pem"
            _log "DH parameters copied from build-time pregenerated file."
        else
            _log "Generating DH parameters (2048-bit) ..."
            openssl dhparam -out "$CERT_DIR/dhparam.pem" 2048
            chmod 644 "$CERT_DIR/dhparam.pem"
            _log "DH parameters written to $CERT_DIR/dhparam.pem"
        fi
    else
        _log "DH parameters already exist — skipping."
    fi
}

_certs_valid() {
    [ -f "$CERT_DIR/fullchain.pem" ] && \
    [ -f "$CERT_DIR/privkey.pem"  ] && \
    [ -f "$CERT_DIR/chain.pem"    ] && \
    openssl x509 -checkend 86400 -noout -in "$CERT_DIR/fullchain.pem" 2>/dev/null
}

_copy_letsencrypt_certs() {
    local domain="$1"
    local live_dir="/etc/letsencrypt/live/$domain"
    _log "Copying Let's Encrypt certificates from $live_dir ..."
    cp -L "$live_dir/fullchain.pem" "$CERT_DIR/fullchain.pem"
    cp -L "$live_dir/privkey.pem"   "$CERT_DIR/privkey.pem"
    cp -L "$live_dir/chain.pem"     "$CERT_DIR/chain.pem"
    chmod 600 "$CERT_DIR/privkey.pem"
    chmod 644 "$CERT_DIR/fullchain.pem" "$CERT_DIR/chain.pem"
}

_ensure_dhparam

if _certs_valid; then
    _log "Valid certificate already exists — skipping generation."
    exit 0
fi

SERVER_IP="${SERVER_IP:-}"
if [ -z "$SERVER_IP" ]; then
    SERVER_IP=$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' | head -1)
fi
if [ -z "$SERVER_IP" ]; then
    SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi
SERVER_IP="${SERVER_IP:-127.0.0.1}"

DOMAIN="${DOMAIN:-}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"

if [ -z "$DOMAIN" ] && [ -n "$SERVER_IP" ]; then
    SSLIP_DOMAIN=$(echo "$SERVER_IP" | tr '.' '-').sslip.io
    _log "No DOMAIN set. Trying Let's Encrypt via sslip.io: $SSLIP_DOMAIN -> $SERVER_IP"
    DOMAIN="$SSLIP_DOMAIN"
fi

if [ -n "$DOMAIN" ] && [ -n "$CERTBOT_EMAIL" ] && command -v certbot >/dev/null 2>&1; then
    _log "Running certbot for domain: $DOMAIN ..."
    if certbot certonly \
        --webroot -w "$ACME_ROOT" \
        -d "$DOMAIN" \
        --email "$CERTBOT_EMAIL" \
        --agree-tos \
        --non-interactive \
        --keep-until-expiring 2>&1; then
        _copy_letsencrypt_certs "$DOMAIN"
        _log "Let's Encrypt certificate obtained for $DOMAIN"
        exit 0
    else
        _log "certbot failed — falling back to self-signed certificate"
    fi
elif [ -n "$DOMAIN" ] && [ -z "$CERTBOT_EMAIL" ]; then
    _log "CERTBOT_EMAIL not set — skipping Let's Encrypt, using self-signed"
fi

_write_selfsigned "${DOMAIN:-localhost}" "$SERVER_IP"
