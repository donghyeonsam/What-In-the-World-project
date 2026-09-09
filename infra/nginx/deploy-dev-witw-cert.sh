#!/bin/bash
set -euo pipefail

# Install as root-owned /usr/local/sbin/deploy-dev-witw-cert.sh.
# Called by ubuntu's acme.sh through sudo -n after install/renew.
if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo: /usr/local/sbin/deploy-dev-witw-cert.sh" >&2
    exit 1
fi

source_dir=/home/ubuntu/certs/dev-witw
target_dir=/etc/nginx/ssl/dev-witw
test -s "$source_dir/dev.witw.kro.kr.key"
test -s "$source_dir/fullchain.cer"
openssl x509 -in "$source_dir/fullchain.cer" -noout -checkend 0
openssl x509 -in "$source_dir/fullchain.cer" -noout -checkhost dev.witw.kro.kr
cert_public=$(openssl x509 -in "$source_dir/fullchain.cer" -pubkey -noout)
key_public=$(openssl pkey -in "$source_dir/dev.witw.kro.kr.key" -pubout)
test "$cert_public" = "$key_public"

install -d -o root -g root -m 700 "$target_dir"
install -o root -g root -m 600 "$source_dir/dev.witw.kro.kr.key" "$target_dir/dev.witw.kro.kr.key"
install -o root -g root -m 644 "$source_dir/fullchain.cer" "$target_dir/fullchain.cer"
/usr/sbin/nginx -t
/usr/bin/systemctl reload nginx
