// Stilen för planmosaikens vektorrutor (Martin) i Origo, med samma färger som GeoServer-stilen och QGIS-projektet.
//
// Origos färdiga bygge innehåller inte tillägget olms (MapLibre-stilar), så stilen registreras här som en egen stiltyp
// med Origos publika addStyleType. Lagret pekar ut den med "custom": { "type": "planmosaik", ... } i index.json.
(function () {
  var COLORS = {
    'gällande, genomförandetiden pågår': [59, 155, 106],
    'gällande, genomförandetiden har gått ut': [138, 148, 160],
    'gällande': [74, 127, 193],
    'antagen': [224, 160, 48]
  };
  var FALLBACK = [136, 136, 136];
  var cache = {};

  function rgba(rgb, alpha) {
    return 'rgba(' + rgb[0] + ',' + rgb[1] + ',' + rgb[2] + ',' + alpha + ')';
  }

  function styleFor(status, label) {
    var key = status + '|' + label;
    if (!cache[key]) {
      var rgb = COLORS[status] || FALLBACK;
      var style = Origo.ol.style;
      cache[key] = new style.Style({
        fill: new style.Fill({ color: rgba(rgb, 0.6) }),
        stroke: new style.Stroke({ color: rgba(rgb, 1), width: 1.5 }),
        text: label ? new style.Text({
          text: label,
          font: 'bold 12px sans-serif',
          fill: new style.Fill({ color: '#1f2933' }),
          stroke: new style.Stroke({ color: '#ffffff', width: 3 }),
          overflow: true
        }) : undefined
      });
    }
    return cache[key];
  }

  // Origo anropar funktionen när lagret skapas och sätter det den returnerar som lagrets stil.
  Origo.Style.addStyleType('planmosaik', function () {
    return function (feature) {
      return styleFor(feature.get('visningsstatus'), feature.get('beteckning'));
    };
  });
}());
