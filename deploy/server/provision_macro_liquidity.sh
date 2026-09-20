#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "run this provisioner as root" >&2
  exit 2
fi

public_key_file="${1:-/tmp/macro_liquidity_deploy.pub}"
unit_file="${2:-/tmp/macro-liquidity-dashboard.service}"
sudoers_file="${3:-/tmp/macro-liquidity-dashboard.sudoers}"
nginx_patcher="${4:-/tmp/patch_nginx_liquidity.py}"
nginx_config="${5:-/etc/nginx/sites-available/default}"
nginx_anchor="${6:-    # macro-liquidity-dashboard insertion point}"

test -s "$public_key_file"
test -s "$unit_file"
test -s "$sudoers_file"
test -s "$nginx_patcher"

if ! id -u macroliq >/dev/null 2>&1; then
  /usr/sbin/useradd --create-home --shell /bin/bash macroliq
fi

/usr/bin/install -d -m 0750 -o macroliq -g macroliq /srv/macro-liquidity-dashboard
/usr/bin/install -d -m 0750 -o macroliq -g macroliq /srv/macro-liquidity-dashboard/releases
/usr/bin/install -d -m 0700 -o macroliq -g macroliq /home/macroliq/.ssh
/usr/bin/install -m 0600 -o macroliq -g macroliq "$public_key_file" /home/macroliq/.ssh/authorized_keys

/usr/bin/install -m 0644 "$unit_file" /etc/systemd/system/macro-liquidity-dashboard.service
/usr/bin/install -m 0440 "$sudoers_file" /etc/sudoers.d/macro-liquidity-dashboard
/usr/sbin/visudo -cf /etc/sudoers.d/macro-liquidity-dashboard

/usr/bin/python3 "$nginx_patcher" --config "$nginx_config" --anchor "$nginx_anchor"
/usr/sbin/nginx -t
/usr/bin/systemctl reload nginx
/usr/bin/systemctl daemon-reload
/usr/bin/systemctl enable macro-liquidity-dashboard.service

echo "macro liquidity production host provisioned"
