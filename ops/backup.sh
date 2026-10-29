#!/bin/bash
# Usage: sudo bash ops/backup.sh /var/backups/college-canteen
set -euo pipefail
umask 077
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
destination=${1:?Specify a backup directory outside the repository}
mkdir -p -- "$destination"
destination=$(cd -- "$destination" && pwd)
case "$destination/" in "$project/"*) echo 'Backup must be outside the repository' >&2; exit 1;; esac
exec 9>"$destination/.backup.lock"
flock -n 9 || { echo 'Backup already running' >&2; exit 1; }
cd "$project"
temporary=$(mktemp "$destination/.database.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
docker compose -f docker-compose.yml exec -T postgres \
  sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$temporary"
# Check the archive catalogue before publishing the backup.
docker compose -f docker-compose.yml exec -T postgres pg_restore --list < "$temporary" > /dev/null
final="$destination/database-$(date -u +%Y%m%dT%H%M%S)-$$.dump"
mv -- "$temporary" "$final"
printf 'Backup created: %s\n' "$final"
# Offsite replication and retention must be configured by the operator.
