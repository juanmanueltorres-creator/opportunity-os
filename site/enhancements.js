/* Opportunity OS: accesos rápidos y radar local de seguimiento.
   No realiza envíos. El Excel se procesa exclusivamente en este navegador. */
(() => {
  'use strict';

  const anchor = document.querySelector('.statrow');
  const today = document.querySelector('.today');
  if (!anchor || !today) return;

  const categories = [
    { label: 'GIS / SIG', term: 'GIS geoespacial' },
    { label: 'Minería / Geología', term: 'geología minería' },
    { label: 'Python / Datos', term: 'Python datos' },
    { label: 'Soporte N1', term: 'soporte técnico' },
    { label: 'Gestión / Operaciones', term: 'encargado operaciones' },
    { label: 'Ventas técnicas', term: 'ventas técnicas' },
    { label: 'Gastronomía', term: 'encargado gastronómico' },
    { label: 'Freelance', term: 'automatización Excel Python' },
    { label: 'QGIS / Teledetección', term: 'QGIS' },
    { label: 'Ambiente / HSE', term: 'medio ambiente' },
    { label: 'Agro / AgTech', term: 'AgTech' },
    { label: 'QA / Testing', term: 'tester QA junior' },
    { label: 'Administración', term: 'administrativo' },
    { label: 'Logística / Depósito', term: 'auxiliar de depósito' },
    { label: 'Diseño / Web', term: 'diseñador web' },
    { label: 'Atención al cliente', term: 'atención al cliente' }
  ];

  const quick = document.createElement('section');
  quick.className = 'quick-panel';
  quick.setAttribute('aria-labelledby', 'quickTitle');
  quick.innerHTML = [
    '<div class="quick-intro"><div><div class="micro eyebrow">ACCESOS DIRECTOS / 01</div>',
    '<h2 id="quickTitle">Buscar trabajo, sin vueltas.</h2>',
    '<p class="note">Elegí una especialidad y abrí una búsqueda real. Argentina completa, sin restringir provincia al comenzar. El idioma de trabajo se verifica en cada aviso.</p></div></div>',
    '<div class="quick-chips" id="quickChips" role="group" aria-label="Búsquedas frecuentes"></div>',
    '<div class="quick-form"><label for="quickQuery">Palabras clave</label><input type="search" id="quickQuery" autocomplete="off" value="GIS" placeholder="Ej.: soporte de aplicaciones, QGIS, encargado"/>',
    '<div id="quickPortalLinks" class="quick-portals" aria-label="Abrir búsqueda en un portal"></div></div>',
    '<div class="quick-utility"><button id="quickSpanish" class="quick-internal" type="button">Ver avisos en español del radar ↓</button>',
    '<a href="https://oportunidades.ypf.com/search/" target="_blank" rel="noopener noreferrer">YPF · Oportunidades ↗</a>',
    '<a href="https://trabajomineria.salta.gob.ar/trabajos/" target="_blank" rel="noopener noreferrer">Minería Salta ↗</a>',
    '<a href="https://www.getonbrd.com/jobs/technical-support" target="_blank" rel="noopener noreferrer">Soporte LATAM ↗</a>',
    '<a href="https://www.bumeran.com.ar/empleos.html" target="_blank" rel="noopener noreferrer">Bumeran ↗</a></div>'
  ].join('');
  anchor.insertAdjacentElement('beforebegin', quick);

  // Guidance remains optional: existing search routes and radar are unchanged.
  const guide = document.createElement('details');
  guide.className = 'quick-guide';
  guide.innerHTML = [
    '<summary>Cómo buscar en cada portal · palabras clave y booleanos</summary>',
    '<div class="quick-guide-body">',
    '<p>Empezá por la especialidad en toda Argentina, sin restringir provincia. Después comprobá ubicación, modalidad, idioma y si el aviso sigue activo.</p>',
    '<p><strong>Ideas de palabras clave por rubro:</strong> elegí una de estas expresiones y pegala en el campo «Palabras clave» de arriba. Probá búsquedas separadas con sinónimos: una sola frase puede dar más resultados que juntar todas.</p>',
    '<ul class="quick-keyword-list">',
    '<li><strong>GIS / geociencias:</strong> <code>GIS</code>, <code>SIG</code>, <code>QGIS</code>, <code>analista geoespacial</code>, <code>teledetección</code>, <code>geología</code>, <code>hidrogeología</code>.</li>',
    '<li><strong>Minería / ambiente:</strong> <code>técnico minero</code>, <code>geotecnia</code>, <code>medio ambiente</code>, <code>HSE</code>, <code>monitoreo ambiental</code>.</li>',
    '<li><strong>Software / datos:</strong> <code>Python junior</code>, <code>backend Python</code>, <code>analista de datos</code>, <code>SQL</code>, <code>Power BI</code>, <code>QA junior</code>.</li>',
    '<li><strong>Soporte / servicios:</strong> <code>soporte técnico N1</code>, <code>mesa de ayuda</code>, <code>help desk</code>, <code>soporte de aplicaciones</code>, <code>atención al cliente</code>.</li>',
    '<li><strong>Gestión / comercio:</strong> <code>encargado de local</code>, <code>operaciones</code>, <code>compras</code>, <code>ventas técnicas</code>, <code>ejecutivo comercial</code>.</li>',
    '<li><strong>Administración / logística:</strong> <code>administrativo</code>, <code>facturación</code>, <code>auxiliar de depósito</code>, <code>control de stock</code>, <code>logística</code>.</li>',
    '<li><strong>Otros sectores:</strong> <code>AgTech</code>, <code>agronomía</code>, <code>diseñador web</code>, <code>gastronomía</code>, <code>freelance Python</code>.</li>',
    '</ul>',
    '<p><strong>Para búsquedas booleanas en LinkedIn:</strong> <code>(&quot;GIS&quot; OR &quot;SIG&quot; OR &quot;QGIS&quot;) AND (&quot;analista&quot; OR &quot;técnico&quot;)</code> o <code>(&quot;soporte técnico&quot; OR &quot;help desk&quot;) NOT &quot;senior&quot;</code>. Usá operadores en mayúsculas. En otros portales empezá con términos simples y sus filtros.</p>',
    '<p><strong>LinkedIn:</strong> admite <code>AND</code>, <code>OR</code>, <code>NOT</code>, comillas y paréntesis. Ejemplo: <code>(&quot;GIS&quot; OR &quot;SIG&quot;) AND (&quot;Python&quot; OR &quot;QGIS&quot;)</code>. <a href="https://www.linkedin.com/help/linkedin/answer/a524335" target="_blank" rel="noopener noreferrer">Guía oficial ↗</a></p>',
    '<p><strong>Indeed:</strong> probá frases exactas como <code>&quot;soporte técnico&quot;</code> o alternativas como <code>GIS OR geología</code>. <a href="https://www.indeed.com/help/job-seekers/articles/204488950-improving-your-job-searches-tips-and-help" target="_blank" rel="noopener noreferrer">Guía oficial ↗</a></p>',
    '<p><strong>Computrabajo:</strong> buscá términos concretos como <code>geología</code>, <code>GIS</code> o <code>soporte técnico</code>. No presupongas que acepta los mismos booleanos que LinkedIn. El enlace de remoto general no incorpora la palabra clave elegida.</p>',
    '<p class="note">Fecha: «Últimos 7 días» se aplica a LinkedIn e Indeed; Computrabajo requiere elegir «Fecha» en su página. Los resultados pueden incluir avisos republicados o actualizados. Estos accesos son búsquedas manuales, no conectores del radar.</p>',
    '</div>'
  ].join('');
  quick.querySelector('.quick-form').insertAdjacentElement('afterend', guide);

  const freshness = document.createElement('div');
  freshness.className = 'quick-freshness';
  freshness.innerHTML = [
    '<label for="quickFreshness">Fecha de publicación</label>',
    '<select id="quickFreshness">',
    '<option value="7" selected>Últimos 7 días</option>',
    '<option value="30">Últimos 30 días</option>',
    '<option value="">Cualquier fecha</option>',
    '</select>',
    '<span class="note">LinkedIn e Indeed usan este filtro en el enlace. En Computrabajo, ajustá «Fecha» dentro del portal. Una publicación actualizada puede ser más antigua.</span>'
  ].join('');
  guide.insertAdjacentElement('beforebegin', freshness);

  const q = quick.querySelector('#quickQuery');
  const chips = quick.querySelector('#quickChips');
  const portals = quick.querySelector('#quickPortalLinks');
  let selected = 0;
  function searchLinks(query) {
    const value = query.trim().slice(0, 120) || 'GIS';
    const days = freshness.querySelector('#quickFreshness').value;
    const linkedinDate = days ? '&f_TPR=r' + (Number(days) * 86400) + '&sortBy=DD' : '';
    const indeedDate = days ? '&fromage=' + days + '&sort=date' : '';
    const compact = value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
      .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    return [
      ['LinkedIn', 'https://www.linkedin.com/jobs/search/?keywords=' + encodeURIComponent(value) + '&location=Argentina&f_WT=2' + linkedinDate],
      ['Indeed', 'https://ar.indeed.com/jobs?q=' + encodeURIComponent(value + ' remoto') + '&l=Argentina' + indeedDate],
      ['Computrabajo · ' + value, 'https://ar.computrabajo.com/trabajo-de-' + compact],
      ['Computrabajo · remoto', 'https://ar.computrabajo.com/trabajo-de-trabajo-remoto-en-remoto'],
      ['Workana · Freelance', 'https://www.workana.com/es/jobs?query=' + encodeURIComponent(value)]
    ];
  }
  function drawLinks() {
    portals.replaceChildren();
    searchLinks(q.value).forEach(([label, url]) => {
      const a = document.createElement('a');
      a.textContent = label + ' ↗';
      a.href = url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.className = 'quick-link';
      portals.append(a);
    });
  }
  function drawChips() {
    chips.replaceChildren();
    categories.forEach((item, index) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'quick-chip' + (index === selected ? ' active' : '');
      b.textContent = item.label;
      b.setAttribute('aria-pressed', String(index === selected));
      b.addEventListener('click', () => {
        selected = index;
        q.value = item.term;
        drawChips();
        drawLinks();
      });
      chips.append(b);
    });
  }
  freshness.querySelector('#quickFreshness').addEventListener('change', drawLinks);
  q.addEventListener('input', () => {
    selected = -1;
    chips.querySelectorAll('button').forEach(b => {
      b.classList.remove('active');
      b.setAttribute('aria-pressed', 'false');
    });
    drawLinks();
  });
  q.value = categories[0].term;
  drawChips();
  drawLinks();
  quick.querySelector('#quickSpanish').addEventListener('click', () => {
    const filter = document.getElementById('listingLanguage');
    if (!filter) return;
    filter.value = 'ES';
    filter.dispatchEvent(new Event('input', { bubbles: true }));
    document.getElementById('cards')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  const tracker = document.createElement('section');
  tracker.className = 'tracker-panel';
  tracker.setAttribute('aria-labelledby', 'trackerTitle');
  tracker.innerHTML = [
    '<div class="tracker-head"><div><div class="micro eyebrow">MI SEGUIMIENTO / EXCEL LOCAL</div>',
    '<h2 id="trackerTitle">Radar de postulaciones y contactos</h2>',
    '<p class="note">Una vista del Excel, no otro registro. Cargalo cuando lo actualices; las marcas del radar público siguen siendo independientes.</p></div>',
    '<div class="tracker-controls"><button class="control primary" id="trackerImport" type="button">Cargar Excel / CSV</button>',
    '<button class="control" id="trackerClear" type="button" hidden>Borrar datos locales</button>',
    '<input type="file" id="trackerFile" accept=".xlsx,.xls,.csv" hidden aria-label="Importar seguimiento desde Excel o CSV"></div></div>',
    '<div id="trackerStatus" role="status" aria-live="polite" class="tracker-status">Sin archivo cargado · Los datos nunca se envían al servidor.</div>',
    '<div class="tracker-body"><div class="tracker-summary">',
    '<div id="trackerDonut" class="tracker-donut" role="img" aria-label="Todavía no hay registros cargados">',
    '<div class="tracker-center"><strong id="trackerTotal">—</strong><span>registros</span></div></div>',
    '<div class="tracker-legend" id="trackerLegend"></div></div>',
    '<div class="tracker-actions"><h3>Próximas gestiones</h3>',
    '<p class="note">Muestra hasta cinco registros con interacción, borrador o seguimiento sugerido por el archivo. Revisá Gmail antes de recontactar.</p>',
    '<div id="trackerNext" class="tracker-next"><p class="note">Cargá tu planilla para ver un resumen. No se modifica el archivo.</p></div>',
    '<p class="note tracker-footnote">Importación manual · Resumen conservado solo en este navegador · El Excel conserva la fuente de verdad.</p></div></div>'
  ].join('');
  today.insertAdjacentElement('beforebegin', tracker);

  const $ = id => tracker.querySelector('#' + id);
  const order = [
    { id: 'pending', label: 'Por investigar / pendientes', color: '#6e837b' },
    { id: 'sent', label: 'Enviados / contacto previo', color: '#80dbe8' },
    { id: 'contact', label: 'Con interacción registrada', color: '#cef482' },
    { id: 'applied', label: 'Postulaciones registradas', color: '#c0a8f2' },
    { id: 'draft', label: 'Borradores', color: '#f4b672' },
    { id: 'other', label: 'Otros / descartados', color: '#d68e85' }
  ];
  const storageKey = 'opportunity-os-tracker-summary-v1';
  const norm = value => String(value == null ? '' : value).normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();

  function classify(value) {
    const s = norm(value);
    if (/descart|rechaz|^on hold|pausad|^killed/.test(s)) return 'other';
    if (/\b(replied|active|inbound|referred)\b|respond|respuesta/.test(s)) return 'contact';
    if (/\bapplied\b|postulad/.test(s)) return 'applied';
    if (/\bdraft\b|borrador/.test(s)) return 'draft';
    if (/\bsent\b|enviad|contacto previo/.test(s)) return 'sent';
    return 'pending';
  }
  function column(head, names) {
    for (const name of names) {
      const idx = head.indexOf(name);
      if (idx >= 0) return idx;
    }
    return -1;
  }
  function fromRows(matrix, sheetName) {
    const limit = Math.min(matrix.length, 10000);
    for (let i = 0; i < Math.min(limit, 10); i += 1) {
      const head = (matrix[i] || []).map(norm);
      const nameCol = column(head, ['empresa / entidad', 'empresa', 'organismo', 'empresa/organizacion', 'empresa / proyecto supabase', 'empresa/organización']);
      const statusCol = column(head, ['estado actual / gmail', 'estado actual', 'estado', 'estado supabase', 'estado consolidado', 'estado gmail comprobado']);
      if (nameCol < 0 || statusCol < 0) continue;
      const actionCol = column(head, ['accion', 'accion siguiente', 'proximo paso', 'proxima accion']);
      const linkCol = column(head, ['gmail · enviado / borrador', 'enlace gmail', 'gmail · evidencia', 'gmail', 'abrir gmail']);
      const dateCol = column(head, ['fecha gmail', 'fecha ultimo envio', 'fecha', 'fecha de envio']);
      const counts = Object.fromEntries(order.map(item => [item.id, 0]));
      let total = 0;
      const records = [];
      for (let j = i + 1; j < limit; j += 1) {
        const row = matrix[j] || [];
        const name = String(row[nameCol] == null ? '' : row[nameCol]).trim();
        const state = String(row[statusCol] == null ? '' : row[statusCol]).trim();
        if (!name || !state) continue;
        const category = classify(state);
        counts[category] += 1;
        total += 1;
        const action = actionCol >= 0 ? String(row[actionCol] || '').slice(0, 170) : '';
        const link = linkCol >= 0 ? String(row[linkCol] || '') : '';
        const href = /^https:\/\/mail\.google\.com\//.test(link) ? link : '';
        const date = dateCol >= 0 ? String(row[dateCol] || '').slice(0, 20) : '';
        records.push({ name: name.slice(0, 95), state: state.slice(0, 85), category, action, href, date });
      }
      if (!total) continue;
      const priority = { contact: 0, draft: 1, applied: 2, sent: 3 };
      const next = records.filter(r => Object.prototype.hasOwnProperty.call(priority, r.category))
        .sort((a, b) => priority[a.category] - priority[b.category])
        .slice(0, 5);
      return { counts, total, next, sheet: sheetName, at: new Date().toISOString() };
    }
    return null;
  }
  function parseCsv(data) {
    const sep = data.split(/\r?\n/, 1)[0].split(';').length > data.split(/\r?\n/, 1)[0].split(',').length ? ';' : ',';
    const rows = []; let row = [], field = '', quoted = false;
    const text = data.replace(/^\uFEFF/, '');
    for (let i = 0; i < text.length; i += 1) {
      const char = text[i];
      if (quoted) {
        if (char === '"' && text[i + 1] === '"') { field += '"'; i += 1; }
        else if (char === '"') quoted = false;
        else field += char;
      } else if (char === '"') quoted = true;
      else if (char === sep) { row.push(field); field = ''; }
      else if (char === '\n') { row.push(field.replace(/\r$/, '')); rows.push(row); row = []; field = ''; }
      else field += char;
    }
    if (field || row.length) { row.push(field.replace(/\r$/, '')); rows.push(row); }
    return rows;
  }

  function render(snapshot) {
    const clear = $('trackerClear');
    clear.hidden = !snapshot;
    if (!snapshot) {
      $('trackerTotal').textContent = '—';
      $('trackerDonut').style.background = '';
      $('trackerDonut').setAttribute('aria-label', 'Sin datos de seguimiento cargados');
      $('trackerLegend').replaceChildren();
      $('trackerNext').replaceChildren();
      const p = document.createElement('p'); p.className = 'note';
      p.textContent = 'Cargá tu Excel o CSV para visualizar el seguimiento.';
      $('trackerNext').append(p);
      $('trackerStatus').textContent = 'Sin archivo cargado · Los datos nunca se envían al servidor.';
      return;
    }
    $('trackerTotal').textContent = String(snapshot.total);
    const colors = []; let start = 0;
    const legend = $('trackerLegend'); legend.replaceChildren();
    order.forEach(item => {
      const value = Number(snapshot.counts[item.id] || 0);
      const end = start + value / snapshot.total * 100;
      colors.push(item.color + ' ' + start.toFixed(3) + '% ' + end.toFixed(3) + '%');
      start = end;
      const line = document.createElement('div'); line.className = 'tracker-legend-row';
      const swatch = document.createElement('span'); swatch.className = 'tracker-swatch'; swatch.style.background = item.color;
      const label = document.createElement('span'); label.textContent = item.label;
      const num = document.createElement('strong'); num.textContent = String(value);
      line.append(swatch, label, num); legend.append(line);
    });
    $('trackerDonut').style.background = 'conic-gradient(' + colors.join(', ') + ')';
    $('trackerDonut').setAttribute('aria-label', snapshot.total + ' registros. ' +
      order.map(item => item.label + ': ' + (snapshot.counts[item.id] || 0)).join('. '));
    const date = new Date(snapshot.at);
    const when = Number.isFinite(date.getTime()) ? new Intl.DateTimeFormat('es-AR', { dateStyle: 'short', timeStyle: 'short' }).format(date) : '';
    $('trackerStatus').textContent = snapshot.total + ' registros · Hoja: ' + snapshot.sheet +
      ' · Cargado ' + when + ' · Sin subir datos a internet';
    const next = $('trackerNext'); next.replaceChildren();
    (snapshot.next || []).forEach(item => {
      const row = document.createElement('div'); row.className = 'tracker-next-row';
      const title = document.createElement('strong'); title.textContent = item.name;
      const meta = document.createElement('small'); meta.textContent = item.state + (item.date ? ' · ' + item.date : '');
      row.append(title, meta);
      if (item.action) {
        const p = document.createElement('p'); p.textContent = item.action; row.append(p);
      }
      if (item.href && /^https:\/\/mail\.google\.com\//.test(item.href)) {
        const a = document.createElement('a'); a.href = item.href; a.textContent = 'Ver correo ↗';
        a.target = '_blank'; a.rel = 'noopener noreferrer'; row.append(a);
      }
      next.append(row);
    });
    if (!snapshot.next || !snapshot.next.length) {
      const p = document.createElement('p'); p.className = 'note'; p.textContent = 'No hay gestiones destacadas en esta importación.'; next.append(p);
    }
  }

  let loader;
  function loadSheetJS() {
    if (window.XLSX) return Promise.resolve(window.XLSX);
    if (loader) return loader;
    loader = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js';
      script.async = true;
      script.onload = () => window.XLSX ? resolve(window.XLSX) : reject(new Error('No se pudo iniciar el lector de Excel.'));
      script.onerror = () => reject(new Error('No se pudo descargar el lector de Excel. Probá con CSV.'));
      document.head.append(script);
    });
    return loader.catch(err => { loader = null; throw err; });
  }

  async function importFile(file) {
    if (!/\.(xlsx|xls|csv)$/i.test(file.name)) throw new Error('Elegí un archivo .xlsx, .xls o .csv.');
    if (file.size > 12 * 1024 * 1024) throw new Error('El archivo supera 12 MB.');
    let snapshot = null;
    if (/\.csv$/i.test(file.name)) {
      snapshot = fromRows(parseCsv(await file.text()), 'CSV');
    } else {
      const XLSX = await loadSheetJS();
      const wb = XLSX.read(new Uint8Array(await file.arrayBuffer()), { type: 'array', dense: true });
      const orderSheets = ['Unificado', 'EMPRESAS_400', 'Seguimiento_200', 'Directorio', 'Enviadas', 'Envíos 29-10'];
      const sheets = [...orderSheets.filter(name => wb.SheetNames.includes(name)), ...wb.SheetNames.filter(name => !orderSheets.includes(name))];
      for (const name of sheets) {
        const rows = XLSX.utils.sheet_to_json(wb.Sheets[name], { header: 1, raw: false, defval: '', blankrows: false });
        snapshot = fromRows(rows, name);
        if (snapshot) break;
      }
    }
    if (!snapshot) throw new Error('No encontré columnas de empresa/organismo y estado. Revisá la planilla.');
    snapshot.file = file.name.slice(0, 120);
    try {
      localStorage.setItem(storageKey, JSON.stringify(snapshot));
    } catch {
      $('trackerStatus').textContent = 'Resumen visible, pero el navegador no permitió guardarlo localmente.';
    }
    render(snapshot);
    // Reutilizar el mismo Excel en el atlas, sin subirlo ni pedirlo dos veces.
    window.dispatchEvent(new CustomEvent('opportunity:local-file', { detail: { file } }));
  }

  $('trackerImport').addEventListener('click', () => $('trackerFile').click());
  $('trackerFile').addEventListener('change', async event => {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    $('trackerImport').disabled = true;
    $('trackerStatus').textContent = 'Leyendo ' + file.name + ' en este navegador…';
    try { await importFile(file); }
    catch (err) { $('trackerStatus').textContent = 'No se pudo importar: ' + (err.message || 'error inesperado'); }
    finally { $('trackerImport').disabled = false; event.target.value = ''; }
  });
  $('trackerClear').addEventListener('click', () => {
    try { localStorage.removeItem(storageKey); } catch {}
    render(null);
  });
  let existing = null;
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey) || 'null');
    if (parsed && Number.isFinite(parsed.total) && parsed.total > 0 && parsed.counts) existing = parsed;
  } catch {}
  render(existing);
})();
