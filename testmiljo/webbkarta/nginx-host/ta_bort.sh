#!/bin/sh
# Tar bort /planmosaik/ ur värdens nginx igen (raden och snippet-filen). Kör med sudo:
#
#   sudo sh ta_bort.sh
set -eu
SITE=/etc/nginx/sites-available/default
SNIPPET=/etc/nginx/snippets/planmosaik.conf
BACKUP="$SITE.bak-planmosaik-borttagning-$(date +%Y%m%d-%H%M%S)"

[ "$(id -u)" = 0 ] || { echo "Kör med sudo."; exit 1; }
cp -p "$SITE" "$BACKUP"
grep -v -F "snippets/planmosaik.conf" "$BACKUP" > "$SITE"
rm -f "$SNIPPET"
if nginx -t; then
    systemctl reload nginx
    echo "Borttaget. Säkerhetskopia: $BACKUP"
else
    echo "nginx -t misslyckades: återställer."
    cp -p "$BACKUP" "$SITE"
    exit 1
fi
