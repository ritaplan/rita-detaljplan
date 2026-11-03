// Stilen för planmosaikens vektorrutor (GeoServer) i Origo: ritar en plankarta som i Rita Detaljplan.
//
//   plan_anvandning  fyllning i Boverkets färg (kolumnen fyllfarg)
//   plan_egenskap    mönster: prickmark, korsmark, ringprickad mark
//   plan_gransar     planområdesgräns > användningsgräns > egenskapsgräns, i Boverkets streckmönster
//
// Mått (pixlar vid referensskalan 1:1000) skalas med kartskalan i band: linjer och mönster blir mindre när man zoomar
// ut och försvinner när de blivit för små. Talen är samma som i ../../stil.py, som GeoServer och QGIS Server bygger på:
// ändra båda när något ändras.
//
// Origos färdiga bygge innehåller inte tillägget olms (MapLibre-stilar), så stilen registreras här som en egen stiltyp
// med Origos publika addStyleType. Lagret pekar ut den med "custom": { "type": "planmosaik", ... } i index.json.
(function () {
  var olStyle = Origo.ol.style;
  var FILL_OPACITY = 0.75;  // användningens färg ligger över grundkartan, som i pluginet (där den multipliceras)

  // --- samma tal som stil.py ---
  var REFERENCE_SCALE = 1000;
  var BAND_EDGES = [0, 1500, 3000, 6000, 12000, 24000, 48000];
  var MAX_ENLARGE = 2;
  var MIN_VISIBLE_GAP = 1.2;
  var MIN_PATTERN_FACTOR = 0.3;
  var MIN_PATTERN_GAP = 3;
  var LINES = {
    egenskapsgrans: { width: 1, dash: [10, 4, 2, 4, 2, 4], minWidth: 0.5, maxScale: 6000, z: 3 },
    anvandningsgrans: { width: 2, dash: [10, 2, 1, 2], minWidth: 0.6, maxScale: 12000, z: 4 },
    planomradesgrans: { width: 3, dash: [16, 4, 4, 4, 16, 4], minWidth: 1, maxScale: null, z: 5 }
  };
  var PATTERNS = {
    prickmark: { shape: 'circle', size: 2, margin: 2.5 },
    korsmark: { shape: 'cross', size: 4.5, margin: 4, stroke: 0.6 },
    ringprickad: { shape: 'ring', size: 4, margin: 4.5, stroke: 0.7 }
  };
  // Kartskalans nämnare för en upplösning (meter per pixel), med OGC:s pixelstorlek 0,28 mm som WMS-tjänsterna
  var PIXEL_SIZE = 0.00028;

  function band(resolution) {
    var scale = resolution / PIXEL_SIZE;
    var index = 0;
    while (index + 1 < BAND_EDGES.length && scale >= BAND_EDGES[index + 1]) {
      index += 1;
    }
    var lower = BAND_EDGES[index];
    var upper = BAND_EDGES[index + 1];
    var representative = upper === undefined ? lower * 1.5 : (lower === 0 ? REFERENCE_SCALE : Math.sqrt(lower * upper));
    return { index: index, lower: lower, factor: Math.min(MAX_ENLARGE, REFERENCE_SCALE / representative) };
  }

  function lineSpec(kind, b) {
    var spec = LINES[kind];
    if (spec.maxScale !== null && b.lower >= spec.maxScale) {
      return null;
    }
    var dash = spec.dash.map(function (value) { return value * b.factor; });
    var minGap = Math.min.apply(null, dash.filter(function (value, i) { return i % 2 === 1; }));
    return { width: Math.max(spec.minWidth, spec.width * b.factor), dash: minGap < MIN_VISIBLE_GAP ? null : dash };
  }

  function patternSpec(kind, b) {
    if (b.factor < MIN_PATTERN_FACTOR) {
      return null;
    }
    var spec = PATTERNS[kind];
    var size = Math.max(1.2, spec.size * b.factor);
    return { shape: spec.shape, size: size, period: Math.max(size + MIN_PATTERN_GAP, (spec.size + spec.margin) * b.factor),
             stroke: Math.max(0.5, (spec.stroke || 0) * b.factor) };
  }

  function rgba(hex, alpha) {
    var n = parseInt((hex || '#f5f5f5').slice(1), 16);
    return 'rgba(' + (n >> 16 & 255) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',' + alpha + ')';
  }

  // Mönstren är förskjutna rad för rad som i pluginet: rutan är dubbelt så hög och har en markör i mitten av första
  // halvan och två halva i kanten av andra, så att den går att lägga sida vid sida utan synlig skarv. Rutans mått
  // avrundas till hela pixlar, så markörerna ligger på ett jämnt avstånd.
  function makePattern(spec) {
    var period = Math.max(3, Math.round(spec.period));
    var canvas = document.createElement('canvas');
    canvas.width = period;
    canvas.height = period * 2;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#000';
    ctx.strokeStyle = '#000';
    ctx.lineWidth = spec.stroke;
    var r = spec.size / 2;
    [[period / 2, period / 2], [0, period * 1.5], [period, period * 1.5]].forEach(function (p) {
      ctx.beginPath();
      if (spec.shape === 'circle') {
        ctx.arc(p[0], p[1], r, 0, 2 * Math.PI);
        ctx.fill();
      } else if (spec.shape === 'cross') {
        ctx.moveTo(p[0] - r, p[1]);
        ctx.lineTo(p[0] + r, p[1]);
        ctx.moveTo(p[0], p[1] - r);
        ctx.lineTo(p[0], p[1] + r);
        ctx.stroke();
      } else {  // ringprickad
        ctx.arc(p[0], p[1], r, 0, 2 * Math.PI);
        ctx.stroke();
      }
    });
    return ctx.createPattern(canvas, 'repeat');
  }

  var cache = {};
  function cached(key, create) {
    if (!(key in cache)) {
      cache[key] = create();
    }
    return cache[key];
  }

  function fillStyle(color) {
    return cached('fill|' + color, function () {
      return new olStyle.Style({ fill: new olStyle.Fill({ color: rgba(color, FILL_OPACITY) }), zIndex: 1 });
    });
  }

  function patternStyle(kind, b) {
    if (!(kind in PATTERNS)) {
      return null;
    }
    return cached('monster|' + kind + '|' + b.index, function () {
      var spec = patternSpec(kind, b);
      return spec ? new olStyle.Style({ fill: new olStyle.Fill({ color: makePattern(spec) }), zIndex: 2 }) : null;
    });
  }

  function lineStyle(kind, b) {
    if (!(kind in LINES)) {
      return null;
    }
    return cached('linje|' + kind + '|' + b.index, function () {
      var spec = lineSpec(kind, b);
      return spec ? new olStyle.Style({
        stroke: new olStyle.Stroke({ color: '#000', width: spec.width, lineDash: spec.dash || undefined,
                                     lineJoin: 'round', lineCap: 'butt' }),
        zIndex: LINES[kind].z
      }) : null;
    });
  }

  // Origo anropar funktionen när lagret skapas och sätter det den returnerar som lagrets stil.
  Origo.Style.addStyleType('planmosaik', function () {
    return function (feature, resolution) {
      switch (feature.get('layer')) {
        case 'plan_anvandning': return fillStyle(feature.get('fyllfarg'));
        case 'plan_egenskap': return patternStyle(feature.get('monster'), band(resolution));
        case 'plan_gransar': return lineStyle(feature.get('typ'), band(resolution));
        default: return null;
      }
    };
  });
}());
