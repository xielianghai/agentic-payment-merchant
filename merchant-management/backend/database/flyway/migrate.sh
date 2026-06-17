#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

set -a
if [[ -f .env ]]; then
  # shellcheck source=/dev/null
  . ./.env
fi
set +a

: "${MYSQL_HOST:=${DB_HOST:-127.0.0.1}}"
: "${MYSQL_PORT:=${DB_PORT:-3306}}"
: "${MYSQL_USER:=${DB_USER:-root}}"
: "${MYSQL_PASSWORD:=${DB_PASSWORD:-12345678}}"
: "${MYSQL_DATABASE:=${DB_NAME:-agentic_merchant_mgmt}}"

if [[ ! "${MYSQL_DATABASE}" =~ ^[a-zA-Z0-9_]+$ ]]; then
  echo "ERROR: invalid MYSQL_DATABASE: ${MYSQL_DATABASE}" >&2
  exit 1
fi

echo "==> Ensuring MySQL database exists: ${MYSQL_DATABASE}"
if command -v mysql >/dev/null 2>&1; then
  MYSQL_PWD="${MYSQL_PASSWORD}" mysql -h"${MYSQL_HOST}" -P"${MYSQL_PORT}" -u"${MYSQL_USER}" \
    -e "CREATE DATABASE IF NOT EXISTS ${MYSQL_DATABASE} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
else
  echo "WARN: mysql CLI not found; assuming database already exists."
fi

JDBC_URL="jdbc:mysql://${MYSQL_HOST}:${MYSQL_PORT}/${MYSQL_DATABASE}?useSSL=false&allowPublicKeyRetrieval=true&characterEncoding=utf8"
MIGRATIONS_DIR="${ROOT}/database/flyway/migrations"

if command -v flyway >/dev/null 2>&1; then
  flyway -url="${JDBC_URL}" -user="${MYSQL_USER}" -password="${MYSQL_PASSWORD}" \
    -locations="filesystem:${MIGRATIONS_DIR}" -baselineOnMigrate=true migrate
elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker_host="${MYSQL_HOST}"
  if [[ "${MYSQL_HOST}" == "127.0.0.1" || "${MYSQL_HOST}" == "localhost" ]]; then
    docker_host="host.docker.internal"
  fi
  docker run --rm --add-host=host.docker.internal:host-gateway \
    -v "${MIGRATIONS_DIR}:/flyway/sql" flyway/flyway:12-alpine \
    -url="jdbc:mysql://${docker_host}:${MYSQL_PORT}/${MYSQL_DATABASE}?useSSL=false&allowPublicKeyRetrieval=true&characterEncoding=utf8" \
    -user="${MYSQL_USER}" -password="${MYSQL_PASSWORD}" -locations=filesystem:/flyway/sql -baselineOnMigrate=true migrate
elif command -v mysql >/dev/null 2>&1; then
  echo "WARN: flyway not found and Docker unavailable; applying idempotent SQL migrations with mysql CLI."
  for migration in "${MIGRATIONS_DIR}"/*.sql; do
    echo "==> Applying ${migration##*/}"
    MYSQL_PWD="${MYSQL_PASSWORD}" mysql -h"${MYSQL_HOST}" -P"${MYSQL_PORT}" -u"${MYSQL_USER}" "${MYSQL_DATABASE}" < "${migration}"
  done
else
  echo "ERROR: install flyway, start Docker, or install mysql CLI to run migrations." >&2
  exit 1
fi
