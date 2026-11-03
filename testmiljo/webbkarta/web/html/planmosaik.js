// Stilen för planmosaikens vektorrutor (Martin) i Origo: ritar en plankarta som i Rita Detaljplan.
//
//   plan_anvandning  fyllning i Boverkets färg (kolumnen fyllfarg)
//   plan_egenskap    mönster: prickmark, korsmark, ringprickad mark
//   plan_gransar     planområdesgräns > användningsgräns > egenskapsgräns, i Boverkets streckmönster
//
// Origos färdiga bygge innehåller inte tillägget olms (MapLibre-stilar), så stilen registreras här som en egen stiltyp
// med Origos publika addStyleType. Lagret pekar ut den med "custom": { "type": "planmosaik", ... } i index.json.
// Mått är i skärmpunkter (streckmönstren är pluginets, i punkter, men ritade i pixlar).
(function () {
  var olStyle = Origo.ol.style;
  var FILL_OPACITY = 0.75;  // användningens färg ligger över grundkartan, som i pluginet (där den multipliceras)

  var LINES = {
    // z-ordning: en högre gräns ritas ovanpå en lägre
    egenskapsgrans: { width: 1, dash: [10, 4, 2, 4, 2, 4], z: 3 },
    anvandningsgrans: { width: 2, dash: [10, 2, 1, 2], z: 4 },
    planomradesgrans: { width: 3, dash: [16, 4, 4, 4, 16, 4], z: 5 }
  };

  function rgba(hex, alpha) {
    var n = parseInt((hex || '#f5f5f5').slice(1), 16);
    return 'rgba(' + (n >> 16 & 255) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',' + alpha + ')';
  }

  // Mönstren är förskjutna rad för rad som i pluginet: rutan är dubbelt så hög och har en prick (eller ett kors) i mitten
  // av första halvan och två halva i kanten av andra, så att den går att lägga sida vid sida utan synlig skarv.
  function makePattern(kind) {
    var period = kind === 'prickmark' ? 7 : 13;
    var canvas = document.createElement('canvas');
    canvas.width = period;
    canvas.height = period * 2;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#000';
    ctx.strokeStyle = '#000';
    var spots = [[period / 2, period / 2], [0, period * 1.5], [period, period * 1.5]];
    spots.forEach(function (p) {
      ctx.beginPath();
      if (kind === 'prickmark') {
        ctx.arc(p[0], p[1], 0.9, 0, 2 * Math.PI);
        ctx.fill();
      } else if (kind === 'korsmark') {
        ctx.lineWidth = 1;
        ctx.moveTo(p[0] - 2.5, p[1]);
        ctx.lineTo(p[0] + 2.5, p[1]);
        ctx.moveTo(p[0], p[1] - 2.5);
        ctx.lineTo(p[0], p[1] + 2.5);
        ctx.stroke();
      } else {  // ringprickad
        ctx.lineWidth = 0.8;
        ctx.arc(p[0], p[1], 1.9, 0, 2 * Math.PI);
        ctx.stroke();
      }
    });
    return canvas.getContext('2d').createPattern(canvas, 'repeat');
  }

  var cache = {};
  function cached(key, create) {
    if (!cache[key]) {
      cache[key] = create();
    }
    return cache[key];
  }

  function fillStyle(color) {
    return cached('fill|' + color, function () {
      return new olStyle.Style({ fill: new olStyle.Fill({ color: rgba(color, FILL_OPACITY) }), zIndex: 1 });
    });
  }

  function patternStyle(kind) {
    return cached('monster|' + kind, function () {
      return new olStyle.Style({ fill: new olStyle.Fill({ color: makePattern(kind) }), zIndex: 2 });
    });
  }

  function lineStyle(kind) {
    var spec = LINES[kind];
    if (!spec) {
      return null;
    }
    return cached('linje|' + kind, function () {
      return new olStyle.Style({
        stroke: new olStyle.Stroke({ color: '#000', width: spec.width, lineDash: spec.dash, lineJoin: 'round' }),
        zIndex: spec.z
      });
    });
  }

  // Origo anropar funktionen när lagret skapas och sätter det den returnerar som lagrets stil.
  Origo.Style.addStyleType('planmosaik', function () {
    return function (feature) {
      switch (feature.get('layer')) {
        case 'plan_anvandning': return fillStyle(feature.get('fyllfarg'));
        case 'plan_egenskap': return patternStyle(feature.get('monster'));
        case 'plan_gransar': return lineStyle(feature.get('typ'));
        default: return null;
      }
    };
  });
}());
