#!/bin/sh
# Hämtar Origo (färdigbyggda filer) till web/html/. Inget byggs och ingen kod körs: bara arkivet hämtas och mappen
# build/ packas upp. Origos repo innehåller de färdiga filerna för varje version.
#
#   sh hamta_origo.sh [version]      (standard: 2.10.0)
#
# OBS: npm-paketet "origo" är något helt annat. Hämta alltid från github.com/origo-map/origo.
# Den färdiga filen innehåller inte tillägget olms (MapLibre-stilar): därför har kartan en egen stil i planmosaik.js.
set -eu
cd "$(dirname "$0")"
VERSION="${1:-2.10.0}"
mkdir -p build web/html
curl -fsSL -o "build/origo-$VERSION.tar.gz" "https://github.com/origo-map/origo/archive/refs/tags/v$VERSION.tar.gz"
sha256sum "build/origo-$VERSION.tar.gz"
# Packa bara upp build/. Egna filer (index.html, index.json, planmosaik.js) skrivs inte över.
tar xzf "build/origo-$VERSION.tar.gz" --strip-components=2 -C web/html \
    --exclude='*/build/index.html' --exclude='*/build/index.json' "origo-$VERSION/build"
# Utvecklingsversionen, dokumentationen och exemplen behövs inte
rm -rf web/html/js/origo.js web/html/origo-documentation web/html/examples web/html/data
echo "Origo $VERSION ligger i web/html/ ($(du -sh web/html | cut -f1))."
