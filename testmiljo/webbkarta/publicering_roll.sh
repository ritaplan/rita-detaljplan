#!/bin/sh
# Skapar databasrollen karta_ro: bara läsrätt på publiceringsvyerna, inget annat.
# Lösenordet slumpas och sparas i .env bredvid den här filen (läsbar bara för dig). Det skrivs aldrig ut.
#
#   sh publicering_roll.sh          (kör på servern, med docker-behörighet)
#
# Förutsätter att databasbehållaren heter postgis och att databasen heter gis. Ändra raderna nedan annars.
set -eu
cd "$(dirname "$0")"
CONTAINER=postgis
DB=gis

if [ -f .env ] && grep -q '^KARTA_RO_PASSWORD=' .env; then
    echo "Rollen finns redan (lösenordet ligger i .env). Ingenting ändrat."
    exit 0
fi

PW=$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | cut -c1-24)
umask 077
printf 'KARTA_RO_PASSWORD=%s\n' "$PW" > .env

# Lösenordet går via stdin och syns inte i processlistan.
docker exec -i "$CONTAINER" sh -c "psql -U \"\$POSTGRES_USER\" -d $DB -v ON_ERROR_STOP=1 -q" <<EOF
CREATE ROLE karta_ro LOGIN PASSWORD '$PW' CONNECTION LIMIT 40;
ALTER ROLE karta_ro SET default_transaction_read_only = on;
ALTER ROLE karta_ro SET statement_timeout = '30s';
GRANT CONNECT ON DATABASE $DB TO karta_ro;
GRANT USAGE ON SCHEMA publicering TO karta_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA publicering TO karta_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA publicering GRANT SELECT ON TABLES TO karta_ro;
EOF
echo "Rollen karta_ro är skapad."
