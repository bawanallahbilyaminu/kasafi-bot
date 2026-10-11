#!/usr/bin/env bash
# Same as push.ps1, for Git Bash / Linux / macOS.
#   ./web/deploy/push.sh user@host [check|deploy|logs|set-engine <url>]
set -euo pipefail
SERVER=${1:?usage: push.sh user@host [check|deploy|logs|set-engine URL]}; ACTION=${2:-deploy}; ARG=${3:-}
REMOTE=/opt/kasafi-web/app/web/deploy/vps-deploy.sh
cd "$(git rev-parse --show-toplevel)"
case $ACTION in
  logs) exec ssh -t "$SERVER" "sudo bash $REMOTE logs" ;;
  set-engine) exec ssh -t "$SERVER" "sudo bash $REMOTE set-engine '$ARG'" ;;
esac
[[ -z "$(git status --porcelain -- web)" ]] || echo "warning: uncommitted changes in web/ will NOT be deployed" >&2
COMMIT=$(git rev-parse --short HEAD)
git archive --format=tar.gz -o /tmp/kasafi-web.tar.gz HEAD web
scp /tmp/kasafi-web.tar.gz "$SERVER:/tmp/kasafi-web.tar.gz"
ssh -t "$SERVER" "set -e; sudo mkdir -p /opt/kasafi-web; cd /opt/kasafi-web; sudo rm -rf app.new; sudo mkdir app.new; \
  sudo tar -xzf /tmp/kasafi-web.tar.gz -C app.new; sudo rm -rf app.old; [ -d app ] && sudo mv app app.old; \
  sudo mv app.new app; echo $COMMIT | sudo tee app/REVISION >/dev/null; rm -f /tmp/kasafi-web.tar.gz; \
  sudo bash $REMOTE $ACTION"
