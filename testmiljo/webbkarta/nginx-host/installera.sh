#!/bin/sh
# Lägger till /planmosaik/ i värdens nginx. Kör med sudo, en gång:
#
#   sudo sh installera.sh
#
# Det här görs (och inget annat):
#   1. säkerhetskopierar sites-available/default
#   2. kopierar planmosaik.conf till /etc/nginx/snippets/
#   3. lägger in EN rad (include) i HTTPS-blocket, direkt efter static-cache-raden
#   4. kontrollerar med nginx -t. Misslyckas det återställs allt och nginx laddas inte om.
#   5. laddar om nginx
# Ta bort det igen med: sudo sh ta_bort.sh
set -eu
cd "$(dirname "$0")"
SITE=/etc/nginx/sites-available/default
SNIPPET=/etc/nginx/snippets/planmosaik.conf
ANCHOR='include /etc/nginx/snippets/static-cache.conf;'
LINE='    include /etc/nginx/snippets/planmosaik.conf;'
BACKUP="$SITE.bak-planmosaik-$(date +%Y%m%d-%H%M%S)"

[ "$(id -u)" = 0 ] || { echo "Kör med sudo."; exit 1; }
grep -q "snippets/planmosaik.conf" "$SITE" && { echo "Redan installerat (raden finns i $SITE). Ingenting ändrat."; exit 0; }
[ "$(grep -c -F "$ANCHOR" "$SITE")" = 1 ] || { echo "Hittar inte ankarraden exakt en gång i $SITE. Avbryter, ingenting ändrat."; exit 1; }

cp -p "$SITE" "$BACKUP"
cp planmosaik.conf "$SNIPPET"
# Raden läggs in direkt efter ankarraden (som finns i HTTPS-blocket)
awk -v anchor="$ANCHOR" -v line="$LINE" '{ print } index($0, anchor) { print line }' "$BACKUP" > "$SITE"

if nginx -t; then
    systemctl reload nginx
    echo "Klart. Säkerhetskopia: $BACKUP"
else
    echo "nginx -t misslyckades: återställer."
    cp -p "$BACKUP" "$SITE"
    rm -f "$SNIPPET"
    nginx -t
    exit 1
fi
