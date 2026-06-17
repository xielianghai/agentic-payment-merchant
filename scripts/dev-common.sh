#!/usr/bin/env bash
# Shared helpers for demo start/stop scripts.
set -euo pipefail

kill_port() {
  local port="$1"
  local pid
  pid=$(lsof -ti tcp:"$port" 2>/dev/null || true)
  if [[ -n "$pid" ]]; then
    echo "  freeing port $port (pid $pid)"
    kill -TERM $pid 2>/dev/null || true
    sleep 0.5
    kill -KILL $pid 2>/dev/null || true
  fi
}

kill_demo_ports() {
  echo "Stopping services on demo ports..."
  for port in 9100 5273 8200 8090 8091 8092 8093 8094 8104 8105 5183; do
    kill_port "$port"
  done
}

wait_for_url() {
  local url="$1"
  local timeout="${2:-30}"
  local i=0
  while [[ "$i" -lt "$timeout" ]]; do
    if curl -sf "$url" >/dev/null 2>&1; then
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done
  return 1
}
