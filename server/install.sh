#!/usr/bin/env bash
# Установка vkgate на сервер (Debian/Ubuntu), запускать от root:
#   bash server/install.sh <VK_APP_ID>
# Ставит Python и Caddy, сервис systemd, HTTPS на адресе <ip>.sslip.io и печатает адрес и ключ для бота.
# Повторный запуск обновляет код и сохраняет ключ и вход.
set -e
APP_ID="${1:?укажите ID приложения VK ID: bash server/install.sh 54841718}"
GROUP_ID=242437734
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$(id -u)" = 0 ] || { echo "запустите от root"; exit 1; }

apt-get update -qq
apt-get install -y -qq python3 curl >/dev/null
if ! command -v caddy >/dev/null; then
  apt-get install -y -qq caddy >/dev/null 2>&1 || {
    apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https gnupg >/dev/null
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq && apt-get install -y -qq caddy >/dev/null
  }
fi

id nmgate >/dev/null 2>&1 || useradd --system --home /var/lib/nmgate --shell /usr/sbin/nologin nmgate
install -d -o nmgate -g nmgate -m 700 /var/lib/nmgate
install -d -m 755 /opt/nmgate
install -m 644 "$HERE/vkgate.py" /opt/nmgate/vkgate.py

if [ ! -f /etc/nmgate.env ]; then
  KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
  printf 'VK_APP_ID=%s\nVK_GROUP_ID=%s\nNM_GATE_KEY=%s\n' "$APP_ID" "$GROUP_ID" "$KEY" > /etc/nmgate.env
fi
sed -i "s/^VK_APP_ID=.*/VK_APP_ID=$APP_ID/" /etc/nmgate.env
chown root:nmgate /etc/nmgate.env; chmod 640 /etc/nmgate.env

cat > /usr/local/bin/vkgate <<'SH'
#!/usr/bin/env bash
exec runuser -u nmgate -- bash -c 'set -a; . /etc/nmgate.env; exec python3 /opt/nmgate/vkgate.py "$@"' _ "$@"
SH
chmod 755 /usr/local/bin/vkgate

cat > /etc/systemd/system/nmgate.service <<'UNIT'
[Unit]
Description=Novostimania VK gateway
After=network-online.target
[Service]
User=nmgate
EnvironmentFile=/etc/nmgate.env
ExecStart=/usr/bin/python3 /opt/nmgate/vkgate.py serve
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable -q nmgate
systemctl restart nmgate

IP="$(curl -4 -s --max-time 10 https://api.ipify.org || hostname -I | awk '{print $1}')"
HOST="${IP//./-}.sslip.io"
CF=/etc/caddy/Caddyfile
if ! grep -q "$HOST" "$CF" 2>/dev/null; then
  if grep -q "/usr/share/caddy" "$CF" 2>/dev/null; then : > "$CF"; fi   # заглушка из пакета — убираем
  printf '\n%s {\n\treverse_proxy 127.0.0.1:8787\n}\n' "$HOST" >> "$CF"
fi
if command -v ufw >/dev/null && ufw status | grep -q active; then ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; fi
systemctl enable -q caddy
systemctl reload caddy 2>/dev/null || systemctl restart caddy

sleep 3
echo
echo "Готово. Для бота (переменные окружения задачи):"
echo "  NM_GATE_URL=https://$HOST"
echo "  NM_GATE_KEY=$(grep ^NM_GATE_KEY= /etc/nmgate.env | cut -d= -f2-)"
echo
echo "Дальше: вход в ВК —  vkgate login-url"
