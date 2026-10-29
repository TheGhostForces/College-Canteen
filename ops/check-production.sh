#!/bin/bash
# Usage: ./ops/check-production.sh https://voscollege.ru
set -euo pipefail
url=${1:-https://voscollege.ru}
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project"
compose=(docker compose -f docker-compose.yml)

curl --fail --silent --show-error --max-time 15 --proto '=https' "$url/api/health" \
  | python3 -I -c 'import json,sys; assert json.load(sys.stdin) == {"status":"ok"}'
for service in postgres app nginx; do
  id=$("${compose[@]}" ps -q "$service")
  test -n "$id" || { echo "CRITICAL: $service missing" >&2; exit 1; }
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id" \
    | grep -Eq '^(healthy|running)$'
done
# Alert before logs/database fill the filesystem.
used=$(df --output=pcent "$project" | tail -1 | tr -dc '0-9')
(( used < 85 )) || { echo "CRITICAL: disk usage ${used}%" >&2; exit 1; }
openssl x509 -checkend 1209600 -noout -in nginx/ssl/fullchain.pem
printf 'OK: HTTPS, database, containers, disk and certificate (>14 days)\n'
