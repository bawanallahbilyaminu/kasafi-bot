#!/usr/bin/env bash
# Kasafi web app: build + run on the VPS with Docker, then publish it at https://$DOMAIN.
#
#   sudo bash vps-deploy.sh check                 what is on ports 80/443, DNS, settings (changes nothing)
#   sudo bash vps-deploy.sh deploy                build, start, health-check, set up the domain
#   sudo bash vps-deploy.sh set-engine <url>      point the web app at a new engine URL (e.g. after a Colab restart)
#   sudo bash vps-deploy.sh logs | status | stop
#
# Settings live in /opt/kasafi-web/web.env (created on first run; chmod 600). Normally run by deploy/push.ps1.
set -euo pipefail

BASE=/opt/kasafi-web
ENVF=$BASE/web.env
APP=$BASE/app/web
DEFAULT_PORT=52723            # K-A-S-A-F on a phone keypad
PORT_RANGE_END=52799
CONTAINER=kasafi-web

c_ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
c_warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
c_err()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; }
step()   { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ask()    { local a; read -r -p "$1 [y/N] " a </dev/tty || a=n; [[ "$a" =~ ^[Yy]$ ]]; }

need_root() { [[ $EUID -eq 0 ]] || { c_err "Run with sudo."; exit 1; }; }

# ------------------------------------------------------------------ settings
write_template() {
  mkdir -p "$BASE"
  cat > "$ENVF" <<'TPL'
# Kasafi web app settings. Private: never commit or share this file.
# Values without quotes; no comments on the same line as a value.

DOMAIN=ai.kasafi.halalnumeriq.com.ng
# email for the Let's Encrypt certificate (only used when this server's own nginx serves the site)
LETSENCRYPT_EMAIL=

# port on this server (localhost only). 52723 = K-A-S-A-F on a phone keypad. Changed automatically if taken.
KASAFI_PORT=52723

# Clerk: dashboard.clerk.com -> your app -> API keys
CLERK_PUBLISHABLE_KEY=
CLERK_SECRET_KEY=

# Kasafi engine (Colab or laptop) and the shared key (same as ENGINE_API_KEY on the engine)
ENGINE_URL=
ENGINE_API_KEY=

# who can open /admin: comma-separated sign-in emails
ADMIN_EMAILS=
TPL
  chmod 600 "$ENVF"
}

load_env() {
  [[ -f "$ENVF" ]] || { write_template; c_warn "Created $ENVF. Fill it in (sudo nano $ENVF), then run deploy again."; exit 2; }
  set -a; # shellcheck disable=SC1090
  . "$ENVF"; set +a
  DOMAIN=${DOMAIN:-ai.kasafi.halalnumeriq.com.ng}
  KASAFI_PORT=${KASAFI_PORT:-$DEFAULT_PORT}
  export VITE_CLERK_PUBLISHABLE_KEY=${VITE_CLERK_PUBLISHABLE_KEY:-${CLERK_PUBLISHABLE_KEY:-}}
  export KASAFI_ENV_FILE=$ENVF KASAFI_PORT
}

check_env() {
  local missing=()
  for k in CLERK_PUBLISHABLE_KEY CLERK_SECRET_KEY ENGINE_URL ENGINE_API_KEY ADMIN_EMAILS; do
    [[ -n "${!k:-}" ]] || missing+=("$k")
  done
  if ((${#missing[@]})); then c_err "Missing in $ENVF: ${missing[*]}"; return 1; fi
  [[ "$CLERK_PUBLISHABLE_KEY" == pk_* ]] || c_warn "CLERK_PUBLISHABLE_KEY should start with pk_"
  [[ "$CLERK_SECRET_KEY" == sk_* ]] || c_warn "CLERK_SECRET_KEY should start with sk_"
  c_ok "settings complete"
}

set_env_value() {   # set_env_value KEY VALUE
  if grep -q "^$1=" "$ENVF"; then sed -i "s|^$1=.*|$1=$2|" "$ENVF"; else echo "$1=$2" >> "$ENVF"; fi
}

# ------------------------------------------------------------------ ports
port_busy() { ss -Hltn "sport = :$1" 2>/dev/null | grep -q .; }
ours_on_port() { docker port "$CONTAINER" 3001 2>/dev/null | grep -q ":$1\$"; }

pick_port() {
  local p=$KASAFI_PORT
  while port_busy "$p" && ! ours_on_port "$p"; do
    c_warn "port $p is taken by another app"
    p=$((p + 1))
    ((p <= PORT_RANGE_END)) || { c_err "no free port between $KASAFI_PORT and $PORT_RANGE_END"; exit 1; }
  done
  if [[ "$p" != "$KASAFI_PORT" ]]; then set_env_value KASAFI_PORT "$p"; KASAFI_PORT=$p; export KASAFI_PORT; fi
  c_ok "app port: 127.0.0.1:$KASAFI_PORT (localhost only)"
}

# ------------------------------------------------------------------ who serves 80/443?
MODE="" PROXY_CONTAINER="" MAILCOW_DIR="" MAILCOW_NET=""
detect_proxy() {
  local proc dock
  proc=$(ss -Hltnp 'sport = :443' 2>/dev/null | sed -n 's/.*users:(("\([^"]*\)".*/\1/p' | head -1 || true)
  dock=$(docker ps --format '{{.Names}} {{.Ports}}' | grep -E '(0\.0\.0\.0|\[::\]|:::)?:443->' | awk '{print $1}' | head -1 || true)
  if [[ -n "$dock" && "$dock" == *nginx-mailcow* ]]; then
    MODE=mailcow PROXY_CONTAINER=$dock
    MAILCOW_DIR=$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$dock" 2>/dev/null || true)
    MAILCOW_NET=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$dock" | tr ' ' '\n' | grep -m1 mailcow || true)
  elif [[ -n "$dock" ]]; then
    MODE=other-container PROXY_CONTAINER=$dock
  elif [[ "$proc" == nginx* ]]; then
    MODE=host-nginx
  elif [[ -n "$proc" ]]; then
    MODE=other-host PROXY_CONTAINER=$proc
  else
    MODE=none
  fi
}

describe_proxy() {
  case $MODE in
    mailcow) c_ok "ports 80/443: mailcow's nginx ($PROXY_CONTAINER), mailcow at ${MAILCOW_DIR:-?}, network ${MAILCOW_NET:-?}" ;;
    host-nginx) c_ok "ports 80/443: nginx on this server" ;;
    other-container) c_warn "ports 80/443: container '$PROXY_CONTAINER' (Traefik / Nginx Proxy Manager / Caddy?)" ;;
    other-host) c_warn "ports 80/443: program '$PROXY_CONTAINER' on this server" ;;
    none) c_warn "nothing is serving ports 80/443 yet" ;;
  esac
}

check_dns() {
  local ip dns
  ip=$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')
  dns=$(getent ahostsv4 "$DOMAIN" | awk '{print $1}' | head -1 || true)
  if [[ -z "$dns" ]]; then c_warn "DNS: $DOMAIN does not resolve yet. Add an A record -> $ip"; return 1
  elif [[ "$dns" != "$ip" ]]; then c_warn "DNS: $DOMAIN -> $dns but this server is $ip"; return 1
  else c_ok "DNS: $DOMAIN -> $ip"; fi
}

# ------------------------------------------------------------------ docker
compose() {
  local files=(-f "$APP/docker-compose.yml")
  [[ -f "$APP/docker-compose.override.yml" ]] && files+=(-f "$APP/docker-compose.override.yml")
  docker compose --project-directory "$APP" --env-file "$ENVF" "${files[@]}" "$@"
}

write_mailcow_override() {
  if [[ $MODE == mailcow && -n "$MAILCOW_NET" ]]; then
    cat > "$APP/docker-compose.override.yml" <<YML
# generated by vps-deploy.sh: joins mailcow's network so mailcow's nginx can reach kasafi-web:3001
services:
  web:
    networks: [default, mailcow]
networks:
  mailcow:
    external: true
    name: $MAILCOW_NET
YML
  else
    rm -f "$APP/docker-compose.override.yml"
  fi
}

wait_healthy() {
  local i
  for i in $(seq 1 40); do
    if curl -fsS --max-time 3 "http://127.0.0.1:$KASAFI_PORT/api/ping" >/dev/null 2>&1; then
      c_ok "web app is up on 127.0.0.1:$KASAFI_PORT"; return 0
    fi
    sleep 2
  done
  c_err "web app did not answer on 127.0.0.1:$KASAFI_PORT. Last logs:"; compose logs --tail 60 web || true; return 1
}

# ------------------------------------------------------------------ reverse proxy
PROXY_BLOCK='
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;          # live progress (Server-Sent Events)
        proxy_cache off;
        proxy_read_timeout 300s;'

setup_host_nginx() {
  local site=/etc/nginx/sites-available/$DOMAIN
  cat > "$site" <<NGX
# Kasafi web app (generated by vps-deploy.sh)
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    client_max_body_size 10m;
    location / {
        proxy_pass http://127.0.0.1:$KASAFI_PORT;$PROXY_BLOCK
    }
}
NGX
  ln -sf "$site" "/etc/nginx/sites-enabled/$DOMAIN"
  nginx -t && systemctl reload nginx && c_ok "nginx site written: $site"
  if [[ -d /etc/letsencrypt/live/$DOMAIN ]]; then
    certbot --nginx -d "$DOMAIN" --non-interactive --redirect --reinstall >/dev/null 2>&1 || true
    c_ok "certificate already present"; return
  fi
  command -v certbot >/dev/null || { ask "Install certbot (Let's Encrypt) now?" && apt-get update -qq && apt-get install -y -qq certbot python3-certbot-nginx; }
  if [[ -z "${LETSENCRYPT_EMAIL:-}" ]]; then c_warn "Set LETSENCRYPT_EMAIL in $ENVF to get HTTPS, then run deploy again."; return; fi
  check_dns || { c_warn "Fix DNS first, then run deploy again for HTTPS."; return; }
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$LETSENCRYPT_EMAIL" --redirect && c_ok "HTTPS enabled"
}

setup_mailcow() {
  [[ -n "$MAILCOW_DIR" && -f "$MAILCOW_DIR/mailcow.conf" ]] || { c_err "Could not find mailcow.conf (looked in '$MAILCOW_DIR')."; return 1; }
  local conf="$MAILCOW_DIR/data/conf/nginx/kasafi-web.conf" listen
  if docker exec "$PROXY_CONTAINER" test -f /etc/nginx/conf.d/listen_ssl.active 2>/dev/null; then
    listen='    include /etc/nginx/conf.d/listen_plain.active;
    include /etc/nginx/conf.d/listen_ssl.active;'
  else
    listen='    listen 80;
    listen [::]:80;
    listen 443 ssl;
    listen [::]:443 ssl;'
  fi
  cat > "$conf" <<NGX
# Kasafi web app (generated by vps-deploy.sh). mailcow loads every *.conf in this folder.
server {
$listen
    server_name $DOMAIN;
    server_tokens off;
    ssl_certificate /etc/ssl/mail/cert.pem;
    ssl_certificate_key /etc/ssl/mail/key.pem;
    client_max_body_size 10m;
    root /web;
    location ^~ /.well-known/acme-challenge/ { allow all; default_type "text/plain"; }
    if (\$scheme = http) { return 301 https://\$host\$request_uri; }
    location / {
        # resolved per request through Docker's DNS: mailcow's nginx still starts if kasafi-web is down
        resolver 127.0.0.11 valid=30s ipv6=off;
        set \$kasafi_upstream http://$CONTAINER:3001;
        proxy_pass \$kasafi_upstream;$PROXY_BLOCK
    }
}
NGX
  if ! docker exec "$PROXY_CONTAINER" nginx -t >/tmp/kasafi-nginx-test 2>&1; then
    c_err "mailcow's nginx rejected the config; removing it so mail is not affected:"; cat /tmp/kasafi-nginx-test
    rm -f "$conf"; return 1
  fi
  docker exec "$PROXY_CONTAINER" nginx -s reload && c_ok "mailcow nginx now serves $DOMAIN -> $CONTAINER:3001"

  # certificate: mailcow's own Let's Encrypt client covers extra names listed in ADDITIONAL_SAN
  local mc="$MAILCOW_DIR/mailcow.conf" san
  if grep -q '^SKIP_LETS_ENCRYPT=y' "$mc"; then c_warn "mailcow has SKIP_LETS_ENCRYPT=y: add a certificate for $DOMAIN yourself."; return; fi
  san=$(grep -E '^ADDITIONAL_SAN=' "$mc" | cut -d= -f2- || true)
  if [[ ",$san," == *",$DOMAIN,"* ]]; then c_ok "mailcow certificate already includes $DOMAIN"; return; fi
  echo
  echo "To get HTTPS, mailcow's certificate must also cover $DOMAIN."
  echo "This adds it to ADDITIONAL_SAN in $mc (backup kept) and restarts mailcow's acme + nginx containers."
  echo "Mail keeps working; webmail may blink for a few seconds."
  check_dns || c_warn "DNS is not pointing here yet, so the certificate request would fail. Fix DNS first."
  if ask "Add $DOMAIN to mailcow's certificate now?"; then
    cp "$mc" "$mc.bak.$(date +%Y%m%d%H%M%S)"
    if [[ -z "$san" ]]; then sed -i "s|^ADDITIONAL_SAN=.*|ADDITIONAL_SAN=$DOMAIN|" "$mc"
    elif grep -q '^ADDITIONAL_SAN=' "$mc"; then sed -i "s|^ADDITIONAL_SAN=.*|ADDITIONAL_SAN=$san,$DOMAIN|" "$mc"
    else echo "ADDITIONAL_SAN=$DOMAIN" >> "$mc"; fi
    (cd "$MAILCOW_DIR" && docker compose up -d >/dev/null && docker compose restart acme-mailcow nginx-mailcow >/dev/null)
    c_ok "certificate requested. Check in 1-2 minutes: docker compose -f $MAILCOW_DIR/docker-compose.yml logs --tail 30 acme-mailcow"
  else
    c_warn "Skipped. The site works over https only after the certificate includes $DOMAIN."
  fi
}

print_manual_proxy() {
  cat <<TXT

Your server's public entrance (ports 80/443) is '$PROXY_CONTAINER', which this script does not configure.
Add a proxy host there:
  domain:  $DOMAIN
  target:  http://127.0.0.1:$KASAFI_PORT      (or, from a container on the same Docker network: http://$CONTAINER:3001)
  options: HTTPS (Let's Encrypt), websockets/streaming on, buffering off, upload limit 10 MB
TXT
}

# ------------------------------------------------------------------ commands
cmd_check() {
  command -v ss >/dev/null || c_warn "'ss' not found (sudo apt install iproute2): port checks are skipped"
  step "Docker"
  docker --version && docker compose version || { c_err "Docker / docker compose plugin missing"; }
  step "Settings ($ENVF)"
  if [[ -f "$ENVF" ]]; then load_env; check_env || true; else c_warn "$ENVF does not exist yet (deploy creates it)"; DOMAIN=ai.kasafi.halalnumeriq.com.ng; KASAFI_PORT=$DEFAULT_PORT; fi
  step "Port"
  if port_busy "$KASAFI_PORT" && ! ours_on_port "$KASAFI_PORT"; then c_warn "$KASAFI_PORT is taken; deploy will pick the next free one"; else c_ok "$KASAFI_PORT is free (or already ours)"; fi
  step "Public entrance (ports 80/443)"
  detect_proxy; describe_proxy
  docker ps --format '  {{.Names}}\t{{.Ports}}' | grep -E ':(80|443)->' || true
  step "DNS"
  check_dns || true
}

cmd_deploy() {
  need_root
  command -v ss >/dev/null || { c_err "'ss' not found: sudo apt install iproute2"; exit 1; }
  [[ -f "$APP/docker-compose.yml" ]] || { c_err "App files not found in $APP (run push.ps1 from your laptop)"; exit 1; }
  step "Settings"; load_env; check_env
  step "Port"; pick_port
  step "Public entrance"; detect_proxy; describe_proxy; write_mailcow_override
  step "Build and start"
  compose build --pull web
  compose up -d --remove-orphans web
  wait_healthy
  if curl -fsS --max-time 10 "http://127.0.0.1:$KASAFI_PORT/api/health" | grep -q '"engine":{'; then c_ok "engine reachable at $ENGINE_URL"
  else c_warn "engine at $ENGINE_URL is not answering (start Colab, then: sudo bash $0 set-engine <new url>)"; fi
  step "Domain: $DOMAIN"
  case $MODE in
    host-nginx) setup_host_nginx ;;
    mailcow) setup_mailcow ;;
    none)
      if ask "Nothing serves ports 80/443. Install nginx + certbot and use them for $DOMAIN?"; then
        apt-get update -qq && apt-get install -y -qq nginx certbot python3-certbot-nginx && setup_host_nginx
      else print_manual_proxy; fi ;;
    *) print_manual_proxy ;;
  esac
  step "Done"
  echo "  Site:    https://$DOMAIN"
  echo "  Local:   http://127.0.0.1:$KASAFI_PORT/api/health"
  echo "  Logs:    sudo bash $0 logs"
  echo "  Engine:  ${ENGINE_URL}  (change with: sudo bash $0 set-engine <url>)"
}

cmd_set_engine() {
  need_root
  local url=${1:-}
  [[ "$url" =~ ^https?:// ]] || { c_err "usage: set-engine https://xxxx.trycloudflare.com"; exit 1; }
  load_env
  set_env_value ENGINE_URL "${url%/}"
  load_env
  compose up -d --no-build --force-recreate web >/dev/null
  wait_healthy
  curl -fsS --max-time 10 "http://127.0.0.1:$KASAFI_PORT/api/health" | grep -q '"engine":{' \
    && c_ok "engine reachable at $ENGINE_URL" || c_warn "web app is up, but the engine at $ENGINE_URL did not answer"
}

case "${1:-}" in
  check) cmd_check ;;
  deploy) cmd_deploy ;;
  set-engine) cmd_set_engine "${2:-}" ;;
  logs) load_env; compose logs -f --tail 100 web ;;
  status) load_env; compose ps; curl -fsS "http://127.0.0.1:$KASAFI_PORT/api/health" || true; echo ;;
  stop) need_root; load_env; compose down ;;
  *) sed -n '2,9p' "$0"; exit 1 ;;
esac
