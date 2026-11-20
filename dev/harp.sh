#!/usr/bin/env sh
# Deploy the release image the way production does: AppAPI → HaRP → Docker, instead of manual-install.
# The Nextcloud developer manual asks for this check before publishing. Run after `make dev-up`.
#
# HaRP reaches ExApps through Nextcloud's own URL under /exapps/, so the web server in front of Nextcloud
# must send /exapps/ to HaRP. The official image's Apache gets that rule here.
set -eu
cd "$(dirname "$0")/.."
OCC=dev/occ
KEY=${HP_SHARED_KEY:-dev-harp-shared-key-0123}
VERSION=$(sed -n "s:.*<version>\(.*\)</version>.*:\1:p" appinfo/info.xml | head -1)
IMAGE=ghcr.io/canakyildz/nextcloud-pinpoint:$VERSION
NETWORK=pinpoint-dev_default

echo "Building $IMAGE"
docker build --target release -t "$IMAGE" .

echo "Starting HaRP"
docker rm -f appapi-harp >/dev/null 2>&1 || true
docker run -d --name appapi-harp -h appapi-harp --network "$NETWORK" \
  -e HP_SHARED_KEY="$KEY" -e NC_INSTANCE_URL=http://nextcloud \
  -v /var/run/docker.sock:/var/run/docker.sock -v pinpoint-harp-certs:/certs \
  ghcr.io/nextcloud/nextcloud-appapi-harp:release >/dev/null

echo "Routing /exapps/ to HaRP"
docker compose -f dev/docker-compose.yml exec -T nextcloud sh -c '
  a2enmod proxy proxy_http >/dev/null
  printf "%s\n" "ProxyPass /exapps/ http://appapi-harp:8780/exapps/" \
                "ProxyPassReverse /exapps/ http://appapi-harp:8780/exapps/" > /etc/apache2/conf-enabled/harp.conf
  apachectl -k graceful'

echo "Registering the HaRP daemon (images from ghcr.io are taken from the local Docker, not pulled)"
$OCC app_api:daemon:register harp_docker "HaRP (Docker)" docker-install http appapi-harp:8780 http://nextcloud \
  --net "$NETWORK" --harp --harp_frp_address appapi-harp:8782 --harp_shared_key "$KEY" 2>/dev/null || true
$OCC app_api:daemon:registry:add harp_docker --registry-from=ghcr.io --registry-to=local 2>/dev/null || true

echo "Deploying Pinpoint through HaRP"
docker compose -f dev/docker-compose.yml stop pinpoint >/dev/null 2>&1 || true
$OCC app_api:app:unregister pinpoint --silent --force 2>/dev/null || true
docker compose -f dev/docker-compose.yml cp appinfo/info.xml nextcloud:/tmp/pinpoint-info.xml
$OCC app_api:app:register pinpoint harp_docker --info-xml /tmp/pinpoint-info.xml --wait-finish
$OCC app_api:app:list
