// Informationspanelen i planmosaiken: ett klick på en plan visar planens uppgifter, handlingarna (plankarta och
// planbeskrivning först) och alla bestämmelser med motiv som gäller i området.
//
// Uppgifterna hämtas med ett enda GetFeatureInfo-anrop till kartservern (lagren planmosaik och plan_bestammelser, se
// publicering.sql): inget eget serverprogram behövs. "Alla bestämmelser i planen" hämtas med WFS.
//
//   PlanMosaikInfo.init(viewer, { infoUrl: 'geoserver/planmosaik/wms', wfsUrl: 'geoserver/planmosaik/ows' })
//
// Allt som kommer ur databasen skrivs in med textContent, aldrig som HTML.
(function () {
  'use strict';

  var LAYERS = 'plan_bestammelser,planmosaik';
  var MONTHS = ['januari', 'februari', 'mars', 'april', 'maj', 'juni', 'juli', 'augusti', 'september', 'oktober',
                'november', 'december'];
  var STATUS = {
    'antagen': { label: 'Antagen', tone: 'amber', note: 'Planen är antagen men har ännu inte vunnit laga kraft.' },
    'gällande': { label: 'Gällande', tone: 'blue', note: '' },
    'gällande, genomförandetiden pågår': { label: 'Gällande', tone: 'green', note: 'Genomförandetiden pågår.' },
    'gällande, genomförandetiden har gått ut': { label: 'Gällande', tone: 'grey', note: 'Genomförandetiden har gått ut.' }
  };
  var PATTERN = {
    prickmark: 'Prickmark',
    korsmark: 'Korsmark',
    ringprickad: 'Ringprickad mark'
  };
  var SVG = 'http://www.w3.org/2000/svg';

  var viewer, map, options, panel, body, highlight, marker, current;

  // --- små hjälpare ---------------------------------------------------------------------------------------------
  function h(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      if (key === 'text') {
        node.textContent = attrs[key];
      } else if (key === 'class') {
        node.className = attrs[key];
      } else if (attrs[key] !== undefined && attrs[key] !== null) {
        node.setAttribute(key, attrs[key]);
      }
    });
    (children || []).forEach(function (child) {
      if (child) {
        node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
      }
    });
    return node;
  }

  function date(text) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(text || '');
    return m ? parseInt(m[3], 10) + ' ' + MONTHS[parseInt(m[2], 10) - 1] + ' ' + m[1] : '';
  }

  function plural(n, one, many) {
    return n + ' ' + (n === 1 ? one : many);
  }

  function parseJson(text, fallback) {
    try {
      return JSON.parse(text);
    } catch (e) {
      return fallback;
    }
  }

  // --- geometri: träffar klicket bestämmelsens egen yta? ----------------------------------------------------
  function inRing(x, y, ring) {
    var inside = false;
    for (var i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
      var xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) {
        inside = !inside;
      }
    }
    return inside;
  }

  function inPolygon(x, y, rings) {
    if (!inRing(x, y, rings[0])) {
      return false;
    }
    for (var i = 1; i < rings.length; i += 1) {
      if (inRing(x, y, rings[i])) {
        return false;
      }
    }
    return true;
  }

  function covers(geometry, coordinate) {
    if (!geometry) {
      return false;
    }
    var x = coordinate[0], y = coordinate[1];
    if (geometry.type === 'Polygon') {
      return inPolygon(x, y, geometry.coordinates);
    }
    if (geometry.type === 'MultiPolygon') {
      return geometry.coordinates.some(function (rings) { return inPolygon(x, y, rings); });
    }
    return false;
  }

  // --- markering på kartan ------------------------------------------------------------------------------------------
  function ensureLayers() {
    if (highlight) {
      return;
    }
    var ol = Origo.ol;
    // group 'none' håller lagren borta ur Origos lagerlista (annars visas de som "Titel saknas")
    highlight = new ol.layer.Vector({ source: new ol.source.Vector(), zIndex: 1000, name: 'planmosaik-markering',
                                      title: 'Markering', group: 'none', queryable: false });
    map.addLayer(highlight);
    marker = new ol.layer.Vector({ source: new ol.source.Vector(), zIndex: 1001, name: 'planmosaik-klickpunkt',
                                   title: 'Klickpunkt', group: 'none', queryable: false });
    map.addLayer(marker);
  }

  function styleFor(kind) {
    var s = Origo.ol.style;
    if (kind === 'area') {
      return new s.Style({ stroke: new s.Stroke({ color: '#e8590c', width: 3 }), fill: new s.Fill({ color: 'rgba(232,89,12,0.07)' }) });
    }
    return new s.Style({ stroke: new s.Stroke({ color: '#1c7ed6', width: 4 }), fill: new s.Fill({ color: 'rgba(28,126,214,0.22)' }),
                         image: new s.Circle({ radius: 7, fill: new s.Fill({ color: '#1c7ed6' }), stroke: new s.Stroke({ color: '#fff', width: 2 }) }) });
  }

  function show(layer, geojson, kind) {
    layer.getSource().clear();
    if (!geojson) {
      return;
    }
    var geometry = typeof geojson === 'string' ? parseJson(geojson, null) : geojson;
    if (!geometry) {
      return;
    }
    var feature = new Origo.ol.format.GeoJSON().readFeature({ type: 'Feature', geometry: geometry, properties: {} });
    feature.setStyle(styleFor(kind));
    layer.getSource().addFeature(feature);
  }

  function showMarker(coordinate) {
    var ol = Origo.ol;
    marker.getSource().clear();
    var feature = new ol.Feature(new ol.geom.Point(coordinate));
    feature.setStyle(new ol.style.Style({ image: new ol.style.Circle({ radius: 6, fill: new ol.style.Fill({ color: '#fff' }),
      stroke: new ol.style.Stroke({ color: '#e8590c', width: 3 }) }) }));
    marker.getSource().addFeature(feature);
  }

  function clearMap() {
    if (highlight) {
      highlight.getSource().clear();
      marker.getSource().clear();
    }
  }

  // --- symboler för bestämmelserna (färg eller mönster) -------------------------------------------------------
  function swatch(row) {
    var svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('viewBox', '0 0 40 40');
    svg.setAttribute('class', 'pm-swatch');
    svg.setAttribute('aria-hidden', 'true');
    function add(name, attrs) {
      var node = document.createElementNS(SVG, name);
      Object.keys(attrs).forEach(function (k) { node.setAttribute(k, attrs[k]); });
      svg.appendChild(node);
      return node;
    }
    add('rect', { x: 1, y: 1, width: 38, height: 38, rx: 8, fill: row.kategori === 'anvandning' ? (row.fyllfarg || '#f5f5f5') : '#fff',
                  stroke: '#9aa5b1', 'stroke-width': 1.2 });
    if (row.monster) {
      for (var x = 8; x <= 32; x += 8) {
        for (var y = 8; y <= 32; y += 8) {
          if (row.monster === 'prickmark') {
            add('circle', { cx: x, cy: y, r: 1.4, fill: '#1f2933' });
          } else if (row.monster === 'korsmark') {
            add('path', { d: 'M' + (x - 2.5) + ' ' + y + 'h5M' + x + ' ' + (y - 2.5) + 'v5', stroke: '#1f2933', 'stroke-width': 1, fill: 'none' });
          } else {
            add('circle', { cx: x, cy: y, r: 2.2, fill: 'none', stroke: '#1f2933', 'stroke-width': 0.9 });
          }
        }
      }
    } else if (row.kategori === 'egenskap') {
      add('path', { d: 'M12 28 L20 10 L28 28 Z', fill: 'none', stroke: '#52606d', 'stroke-width': 1.6, 'stroke-linejoin': 'round' });
    }
    return svg;
  }

  // --- bestämmelsekort ------------------------------------------------------------------------------------------
  function card(row, opts) {
    opts = opts || {};
    var label = row.beteckning || (row.monster ? PATTERN[row.monster] : '');
    var head = h('div', { class: 'pm-card-head' }, [
      label ? h('span', { class: 'pm-code', text: label }) : null,
      h('span', { class: 'pm-kind', text: row.kategori === 'anvandning' ? 'Användning' : 'Egenskap' }),
      opts.here ? h('span', { class: 'pm-here', text: 'Gäller här' }) : null
    ]);
    var text = h('p', { class: 'pm-text', text: row.text || '' });
    var motiv;
    if (row.motiv) {
      var motivText = h('p', { text: row.motiv });
      motiv = opts.collapsed
        ? h('details', { class: 'pm-motiv' }, [h('summary', { text: 'Motiv' }), motivText])
        : h('div', { class: 'pm-motiv pm-motiv-open' }, [h('span', { class: 'pm-motiv-label', text: 'Motiv' }), motivText]);
    } else {
      motiv = h('p', { class: 'pm-motiv-none', text: 'Inget motiv är angivet.' });
    }
    var main = h('div', { class: 'pm-card-main' }, [head, text, motiv]);
    var node = h('article', { class: 'pm-card' + (opts.here ? ' is-here' : '') }, [swatch(row), main]);
    node.addEventListener('mouseenter', function () { show(highlight, row.egen_geojson, 'hover'); });
    node.addEventListener('mouseleave', function () { restoreArea(); });
    return node;
  }

  function restoreArea() {
    if (current && current.areaGeometry) {
      show(highlight, current.areaGeometry, 'area');
    } else {
      highlight.getSource().clear();
    }
  }

  // --- uppgifter om planen ------------------------------------------------------------------------------------
  function statusBlock(plan) {
    var status = STATUS[plan.visningsstatus] || { label: plan.status || '', tone: 'grey', note: '' };
    var note = status.note;
    if (plan.visningsstatus === 'gällande, genomförandetiden pågår' && plan.genomforandetid_utgar) {
      note = 'Genomförandetiden pågår till och med ' + date(plan.genomforandetid_utgar) + '.';
    } else if (plan.visningsstatus === 'gällande, genomförandetiden har gått ut' && plan.genomforandetid_utgar) {
      note = 'Genomförandetiden gick ut ' + date(plan.genomforandetid_utgar) + '.';
    }
    return h('div', { class: 'pm-status' }, [
      h('span', { class: 'pm-badge tone-' + status.tone }, [h('span', { class: 'pm-dot' }), status.label]),
      note ? h('span', { class: 'pm-status-note', text: note }) : null
    ]);
  }

  function documentLink(doc, main) {
    var name = doc.namn || 'Handling';
    var ext = (/\.([a-z0-9]{2,4})(?:[?#]|$)/i.exec(doc.lank || '') || [])[1];
    var meta = [date(doc.datum), ext ? ext.toUpperCase() : ''].filter(Boolean).join(' · ');
    return h('a', { class: 'pm-doc' + (main ? ' pm-doc-main' : ''), href: doc.lank, target: '_blank', rel: 'noopener' }, [
      h('span', { class: 'pm-doc-icon', text: ext ? ext.toUpperCase() : 'LÄNK' }),
      h('span', { class: 'pm-doc-text' }, [h('strong', { text: name }), meta ? h('small', { text: meta }) : null]),
      h('span', { class: 'pm-doc-go', text: '↗', 'aria-hidden': 'true' })
    ]);
  }

  function documentsBlock(plan) {
    var docs = parseJson(plan.handlingar, []).filter(function (d) { return d && /^https?:\/\//.test(d.lank || ''); });
    var section = h('section', { class: 'pm-section' }, [h('h3', { text: 'Handlingar' })]);
    if (!docs.length) {
      section.appendChild(h('p', { class: 'pm-muted', text: 'Inga handlingar är kopplade till planen.' }));
      return section;
    }
    var main = docs.filter(function (d) { return d.innehall === 'plankarta' || d.roll === 'planbeskrivning'; });
    var rest = docs.filter(function (d) { return main.indexOf(d) < 0; });
    var grid = h('div', { class: 'pm-docs-main' });
    main.forEach(function (d) { grid.appendChild(documentLink(d, true)); });
    section.appendChild(grid);
    if (rest.length) {
      var list = h('div', { class: 'pm-docs-rest' });
      rest.forEach(function (d) { list.appendChild(documentLink(d, false)); });
      section.appendChild(h('h4', { text: 'Övriga handlingar' }));
      section.appendChild(list);
    }
    return section;
  }

  function factsBlock(plan) {
    var facts = [['Antagen', date(plan.datum_antagande)], ['Laga kraft', date(plan.datum_laga_kraft)]];
    if (plan.genomforandetid_manader) {
      var years = plan.genomforandetid_manader / 12;
      facts.push(['Genomförandetid', (years % 1 === 0 ? plural(years, 'år', 'år') : plural(plan.genomforandetid_manader, 'månad', 'månader')) +
                  (plan.genomforandetid_utgar ? ' (till ' + date(plan.genomforandetid_utgar) + ')' : '')]);
    }
    var list = h('dl', { class: 'pm-facts' });
    facts.filter(function (f) { return f[1]; }).forEach(function (f) {
      list.appendChild(h('div', {}, [h('dt', { text: f[0] }), h('dd', { text: f[1] })]));
    });
    var section = h('section', { class: 'pm-section' }, [h('h3', { text: 'Om planen' })]);
    if (plan.syfte) {
      section.appendChild(h('p', { class: 'pm-purpose', text: plan.syfte }));
    }
    section.appendChild(list);
    return section;
  }

  // --- bestämmelser --------------------------------------------------------------------------------------------
  function unique(rows) {
    // samma bestämmelse kan ligga på flera egenskapsytor: visa den en gång, och som "här" om någon av dem gäller här
    var seen = {};
    var out = [];
    rows.forEach(function (row) {
      var key = [row.kategori, row.beteckning, row.monster, row.text, row.motiv].join('|');
      if (seen[key] === undefined) {
        seen[key] = out.length;
        out.push(row);
      } else if (row._here) {
        out[seen[key]]._here = true;
        out[seen[key]].egen_geojson = row.egen_geojson;
      }
    });
    return out;
  }

  function orderRows(rows) {
    return rows.slice().sort(function (a, b) {
      return (a.ordning - b.ordning) || String(a.beteckning || '').localeCompare(String(b.beteckning || ''), 'sv');
    });
  }

  function areaTitle(area) {
    return [area.beteckning, area.anvandningsform].filter(Boolean).join(' · ');
  }

  function rulesBlock(areas, coordinate) {
    var section = h('section', { class: 'pm-section' }, [h('h3', { text: 'Bestämmelser här' })]);
    areas.forEach(function (area) {
      var use = orderRows(area.rows.filter(function (r) { return r.kategori === 'anvandning'; }));
      var allProperty = area.rows.filter(function (r) { return r.kategori === 'egenskap'; });
      allProperty.forEach(function (r) { r._here = covers(parseJson(r.egen_geojson, null), coordinate); });
      var property = unique(allProperty);
      var here = orderRows(property.filter(function (r) { return r._here; }));
      var other = orderRows(property.filter(function (r) { return !r._here; }));

      section.appendChild(h('div', { class: 'pm-area' }, [
        h('span', { class: 'pm-area-label', text: 'Området du klickade i' }),
        h('strong', { text: areaTitle(area) || 'Område' })
      ]));
      if (use.length) {
        section.appendChild(h('h4', { text: 'Användning' }));
        use.forEach(function (r) { section.appendChild(card(r)); });
      }
      if (here.length) {
        section.appendChild(h('h4', { class: 'pm-h-here', text: 'Egenskaper där du klickade' }));
        here.forEach(function (r) { section.appendChild(card(r, { here: true })); });
      }
      if (other.length) {
        var details = h('details', { class: 'pm-more' }, [
          h('summary', { text: 'Övriga egenskaper i området (' + other.length + ')' })
        ]);
        other.forEach(function (r) { details.appendChild(card(r, { collapsed: true })); });
        section.appendChild(details);
      }
      if (!use.length && !here.length && !other.length) {
        section.appendChild(h('p', { class: 'pm-muted', text: 'Området har inga bestämmelser.' }));
      }
    });
    return section;
  }

  function allRulesBlock(plan) {
    var section = h('section', { class: 'pm-section' });
    var button = h('button', { class: 'pm-button', type: 'button', text: 'Visa alla bestämmelser i planen' });
    var result = h('div', { class: 'pm-all' });
    if (!options.wfsUrl) {
      return null;
    }
    button.addEventListener('click', function () {
      button.disabled = true;
      button.textContent = 'Hämtar…';
      var params = new URLSearchParams({ service: 'WFS', version: '2.0.0', request: 'GetFeature', typeNames: 'plan_bestammelser',
        outputFormat: 'application/json', cql_filter: "plan='" + String(plan.plan).replace(/'/g, "''") + "'",
        propertyName: 'plan,omrade_id,omrade_beteckning,anvandningsform,kategori,beteckning,ordning,text,motiv,monster,fyllfarg,egen_geojson' });
      fetch(options.wfsUrl + '?' + params.toString()).then(function (r) { return r.json(); }).then(function (json) {
        var areas = groupAreas((json.features || []).map(function (f) { return f.properties; }));
        result.textContent = '';
        areas.forEach(function (area) {
          var rows = orderRows(area.rows.filter(function (r) { return r.kategori === 'anvandning'; }))
            .concat(orderRows(unique(area.rows.filter(function (r) { return r.kategori === 'egenskap'; }))));
          var details = h('details', { class: 'pm-more' }, [h('summary', { text: areaTitle(area) + ' (' + plural(rows.length, 'bestämmelse', 'bestämmelser') + ')' })]);
          rows.forEach(function (r) { details.appendChild(card(r, { collapsed: true })); });
          result.appendChild(details);
        });
        button.remove();
      }).catch(function () {
        button.disabled = false;
        button.textContent = 'Kunde inte hämta. Försök igen';
      });
    });
    section.appendChild(button);
    section.appendChild(result);
    return section;
  }

  function groupAreas(rows) {
    var byId = {};
    var order = [];
    rows.forEach(function (row) {
      if (!byId[row.omrade_id]) {
        byId[row.omrade_id] = { beteckning: row.omrade_beteckning, anvandningsform: row.anvandningsform, rows: [] };
        order.push(row.omrade_id);
      }
      byId[row.omrade_id].rows.push(row);
    });
    return order.map(function (id) { return byId[id]; });
  }

  // --- hela panelen --------------------------------------------------------------------------------------------
  function render(data, coordinate) {
    body.textContent = '';
    var plan = data.plan;
    var areas = groupAreas(data.rows);
    current = { areaGeometry: null };
    var useRow = data.rows.filter(function (r) { return r.kategori === 'anvandning'; })[0];
    if (useRow) {
      current.areaGeometry = useRow.egen_geojson;
    }
    restoreArea();

    var hero = h('header', { class: 'pm-hero' }, [
      h('div', { class: 'pm-eyebrow', text: ['Detaljplan', plan.kommun].filter(Boolean).join(' · ') }),
      h('h2', { class: 'pm-title', id: 'pm-title', text: plan.namn || plan.beteckning || 'Detaljplan' }),
      h('div', { class: 'pm-meta', text: [plan.beteckning, plan.diarienummer ? 'Dnr ' + plan.diarienummer : ''].filter(Boolean).join(' · ') }),
      statusBlock(plan)
    ]);
    body.appendChild(hero);
    body.appendChild(documentsBlock(plan));
    body.appendChild(factsBlock(plan));
    if (areas.length) {
      body.appendChild(rulesBlock(areas, coordinate));
    }
    var all = allRulesBlock(plan);
    if (all) {
      body.appendChild(all);
    }
    body.scrollTop = 0;
  }

  function message(title, text) {
    body.textContent = '';
    body.appendChild(h('div', { class: 'pm-message' }, [h('strong', { text: title }), h('p', { text: text })]));
  }

  function loading() {
    body.textContent = '';
    body.appendChild(h('div', { class: 'pm-skeleton', 'aria-hidden': 'true' }, [
      h('div', { class: 'sk sk-l' }), h('div', { class: 'sk sk-xl' }), h('div', { class: 'sk sk-m' }), h('div', { class: 'sk sk-box' }),
      h('div', { class: 'sk sk-box' })
    ]));
    body.setAttribute('aria-busy', 'true');
  }

  function open() {
    fitToFooter();
    panel.hidden = false;
    panel.classList.add('is-open');
  }

  function close() {
    panel.hidden = true;
    panel.classList.remove('is-open');
    current = null;
    clearMap();
  }

  // --- anrop ----------------------------------------------------------------------------------------------------
  function ask(coordinate, pixel) {
    var size = map.getSize();
    var extent = map.getView().calculateExtent(size);
    var params = new URLSearchParams({
      SERVICE: 'WMS', VERSION: '1.1.1', REQUEST: 'GetFeatureInfo', LAYERS: LAYERS, QUERY_LAYERS: LAYERS, STYLES: '',
      SRS: viewer.getProjectionCode(), BBOX: extent.join(','), WIDTH: Math.round(size[0]), HEIGHT: Math.round(size[1]),
      X: Math.round(pixel[0]), Y: Math.round(pixel[1]), INFO_FORMAT: 'application/json', FEATURE_COUNT: '200'
    });
    return fetch(options.infoUrl + '?' + params.toString()).then(function (response) {
      if (!response.ok) {
        throw new Error('HTTP ' + response.status);
      }
      return response.json();
    });
  }

  function sort(json) {
    var plan = null;
    var rows = [];
    (json.features || []).forEach(function (f) {
      var p = f.properties || {};
      if ('kategori' in p) {
        rows.push(p);
      } else if ('visningsstatus' in p && 'namn' in p) {
        plan = plan || p;
      }
    });
    return { plan: plan, rows: rows };
  }

  var token = 0;
  function onClick(event) {
    var mine = (token += 1);
    showMarker(event.coordinate);
    open();
    loading();
    ask(event.coordinate, event.pixel).then(function (json) {
      if (mine !== token) {
        return;
      }
      body.removeAttribute('aria-busy');
      var data = sort(json);
      if (!data.plan) {
        close();
        toast('Det finns ingen detaljplan här.');
        return;
      }
      render(data, event.coordinate);
      panel.focus({ preventScroll: true });
    }).catch(function () {
      if (mine === token) {
        body.removeAttribute('aria-busy');
        message('Uppgifterna kunde inte hämtas', 'Kartservern svarade inte. Försök igen om en stund.');
      }
    });
  }

  var toastTimer;
  function toast(text) {
    var node = document.getElementById('pm-toast') || document.body.appendChild(h('div', { id: 'pm-toast', class: 'pm-toast', role: 'status' }));
    node.textContent = text;
    node.classList.add('is-visible');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { node.classList.remove('is-visible'); }, 2600);
  }

  // Origos bottenlist (kartans namn, skala, koordinatsystem) ska inte täckas: panelen läggs ovanför den, vilken höjd den än har
  function fitToFooter() {
    var footer = document.querySelector('.o-footer');
    document.documentElement.style.setProperty('--pm-footer', ((footer && footer.offsetHeight) || 28) + 'px');
  }

  function init(v, opts) {
    viewer = v;
    options = opts || {};
    map = viewer.getMap();
    ensureLayers();
    panel = h('aside', { class: 'pm-panel', hidden: '', tabindex: '-1', 'aria-labelledby': 'pm-title' });
    var closeButton = h('button', { class: 'pm-close', type: 'button', 'aria-label': 'Stäng', text: '×' });
    closeButton.addEventListener('click', close);
    body = h('div', { class: 'pm-body' });
    panel.appendChild(closeButton);
    panel.appendChild(body);
    document.body.appendChild(panel);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !panel.hidden) {
        close();
      }
    });
    map.on('singleclick', onClick);
    fitToFooter();
    window.addEventListener('resize', fitToFooter);
    setTimeout(fitToFooter, 1500); // bottenlisten byggs färdigt strax efter att kartan laddats
  }

  window.PlanMosaikInfo = { init: init };
}());
