#!/usr/bin/env bash
#
# ProxyHub deployment bootstrap.
#
# Copies .env.example to .env and fills in freshly generated secrets so a new
# deployment can start without hand-editing placeholder values.
#
# Usage:
#   ./seed.sh           # create .env (refuses to overwrite an existing one)
#   ./seed.sh --force   # recreate .env, replacing an existing one
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT/.env"
EXAMPLE_FILE="$ROOT/.env.example"
FORCE=0

for arg in "$@"; do
  case "$arg" in
    -f|--force) FORCE=1 ;;
    -h|--help)
      sed -n '3,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "seed.sh: unknown argument: $arg" >&2
      echo "Try './seed.sh --help'." >&2
      exit 2
      ;;
  esac
done

if [ ! -f "$EXAMPLE_FILE" ]; then
  echo "seed.sh: $EXAMPLE_FILE not found (run from the repo root)." >&2
  exit 1
fi

if [ -f "$ENV_FILE" ] && [ "$FORCE" -ne 1 ]; then
  echo "seed.sh: .env already exists; refusing to overwrite (use --force)." >&2
  exit 1
fi

# --- secret generation -------------------------------------------------------

gen_hex() {
  # $1 = number of random bytes; prints 2*$1 hex characters.
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$1"
  elif [ -r /dev/urandom ]; then
    head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'
  else
    echo "seed.sh: need openssl or /dev/urandom to generate secrets." >&2
    exit 1
  fi
}

gen_password() {
  # URL/YAML-safe password: alphanumerics only, so it cannot break the
  # DB_URL that build_db_url() assembles or the docker-compose interpolation.
  gen_hex 16 | tr -dc 'A-Za-z0-9'
}

# --- writing values into .env ------------------------------------------------

set_var() {
  # $1 = KEY, $2 = value. Replaces the KEY=... line, or appends if absent.
  local key="$1" value="$2"
  if grep -qE "^${key}=" "$ENV_FILE"; then
    # '|' delimiter keeps the value's characters from breaking the pattern.
    sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    rm -f "$ENV_FILE.bak"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

echo "+ creating .env from .env.example"
cp "$EXAMPLE_FILE" "$ENV_FILE"

echo "+ generating secrets"
set_var APP_KEY "$(gen_hex 32)"
set_var INTERNAL_API_KEY "$(gen_hex 24)"
set_var DB_PASSWORD "$(gen_password)"

# --- summary -----------------------------------------------------------------

echo ""
echo "Done. Seeded .env with fresh values for:"
echo "  APP_KEY, INTERNAL_API_KEY, DB_PASSWORD"
echo ""
echo "Review .env before deploying (database host/credentials, ports)."
