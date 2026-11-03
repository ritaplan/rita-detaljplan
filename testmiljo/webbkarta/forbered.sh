#!/bin/sh
# Förbereder lösenord och filer som docker-compose.yml behöver. Kan köras om: det som redan finns lämnas orört.
#
#   sh forbered.sh      (kör på servern, i mappen med docker-compose.yml, efter publicering_roll.sh)
#
# Skapar: GEOSERVER_ADMIN_PASSWORD i .env, qgis/pg_service.conf (databasuppgifterna som QGIS Server läser).
set -eu
cd "$(dirname "$0")"
umask 077

[ -f .env ] && grep -q '^KARTA_RO_PASSWORD=' .env || { echo "Kör publicering_roll.sh först."; exit 1; }
grep -q '^GEOSERVER_ADMIN_PASSWORD=' .env || \
    printf 'GEOSERVER_ADMIN_PASSWORD=%s\n' "$(head -c 24 /dev/urandom | base64 | tr -d '/+=' | cut -c1-24)" >> .env

mkdir -p qgis web/html
chmod 755 qgis web web/html
# Filen läses av QGIS Server i behållaren och måste därför vara läsbar för den.
PW=$(sed -n 's/^KARTA_RO_PASSWORD=//p' .env)
cat > qgis/pg_service.conf <<EOF
[planmosaik]
host=postgis
port=5432
dbname=gis
user=karta_ro
password=$PW
sslmode=require
EOF
chmod 644 qgis/pg_service.conf
echo "Klart."
