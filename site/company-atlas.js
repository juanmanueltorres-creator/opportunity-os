/* Opportunity OS — atlas privado: empresas y organismos por jurisdicción.
   Solo lee archivos elegidos por la persona. No hay API de escritura ni red. */
(() => {
  'use strict';
  const before = document.querySelector('.tracker-panel') || document.querySelector('.today');
  if (!before) return;

  const PROVINCES = [
    'Buenos Aires','CABA','Catamarca','Chaco','Chubut','Córdoba','Corrientes',
    'Entre Ríos','Formosa','Jujuy','La Pampa','La Rioja','Mendoza','Misiones',
    'Neuquén','Río Negro','Salta','San Juan','San Luis','Santa Cruz','Santa Fe',
    'Santiago del Estero','Tierra del Fuego','Tucumán'
  ];
  const SECTORS = ['Geociencias / GIS','Minería','Tecnología / datos','Energía',
    'Ambiente','Agro','Turismo','Innovación / ciencia','Gestión / operaciones','Otros'];
  const OFFICIAL = [
    ['CEP XXI · Mapa productivo-laboral','https://www.argentina.gob.ar/produccion/cep/tableros-interactivos','Establecimientos, empleo y sectores. Datos agregados: no identifica una contratación.'],
    ['CEP XXI · Dataset de establecimientos','https://datos.gob.ar/dataset/produccion-distribucion-geografica-establecimientos-productivos','Descarga pública de información territorial de establecimientos y empleo por actividad.'],
    ['OEDE · Empleo y empresas','https://www.argentina.gob.ar/trabajo/estadisticas/oede-estadisticas-provinciales','Empresas, puestos y tamaño por jurisdicción y actividad.'],
    ['SIACAM · Minería','https://www.argentina.gob.ar/economia/mineria/siacam','Proyectos, cadenas y estadísticas mineras.'],
    ['Agencia I+D+i · Adjudicaciones por provincia','https://www.argentina.gob.ar/ciencia/agencia/ueac-informes-y-publicaciones/informes-provinciales','Montos y proyectos adjudicados por provincia; no implica inversión ejecutada ni contratación.'],
    ['Fundar · Monitor de Empresas','https://empresas.fund.ar/','Empresas empleadoras según SRT; gráficos públicos por sector, provincia y tamaño.'],
    ['OPC · Inversión pública por provincia','https://opc.gob.ar/monitores/inversion-publica-de-la-administracion-nacional/','Mapa y montos de proyectos de inversión pública (BAPIN / e-Sidif); no son presupuestos de cada empresa.'],
    ['Registro Nacional de Sociedades','https://www.argentina.gob.ar/node/143590','Datos societarios por consulta puntual; no equivale a vacante.'],
    ['Georef · Provincias oficiales','https://www.argentina.gob.ar/georef/descarga-de-la-base-completa','Nomenclador de jurisdicciones; no geocodifica empresas automáticamente.']
  ];
  const SECTION = document.createElement('section');
  SECTION.id = 'atlas-empresas';
  SECTION.className = 'company-atlas';
  SECTION.setAttribute('aria-labelledby','atlasTitle');
  SECTION.innerHTML = [
    '<div class="atlas-top"><div><span class="micro eyebrow">ATLAS PRODUCTIVO · ARGENTINA + LATAM</span>',
    '<h2 id="atlasTitle">Empresas, organismos y contactos</h2>',
    '<p class="note">Como un SIACAM laboral: explorá por provincia, país, actividad y seguimiento. Se diferencia el directorio propio de la estadística oficial. Los datos privados nunca se publican.</p></div>',
    '<div class="atlas-import">',
    '<button type="button" class="control primary" id="atlasUpload">Sumar Excel / directorio</button>',
    '<button type="button" class="control" id="atlasErase" hidden>Borrar atlas local</button>',
    '<input type="file" id="atlasFiles" accept=".xlsx,.xls,.csv" multiple hidden aria-label="Importar planillas del atlas">',
    '</div></div>',
    '<div id="atlasStatus" class="atlas-status" role="status" aria-live="polite">Para empezar, cargá tu Excel de empresas y el directorio federal; no hace falta editar el sitio.</div>',
    '<div class="atlas-stats"><div><strong id="atlasCount">—</strong><span>Organizaciones</span></div>',
    '<div><strong id="atlasKnown">—</strong><span>Con provincia identificada</span></div>',
    '<div><strong id="atlasAgencies">—</strong><span>Organismos públicos / científicos</span></div>',
    '<div><strong id="atlasMoved">—</strong><span>Con contacto / envío registrado</span></div></div>',
    '<div class="atlas-controls">',
    '<label>Buscar<input id="atlasSearch" type="search" placeholder="Empresa, organismo, GIS, turismo…" autocomplete="off"></label>',
    '<label>País<select id="atlasCountry"><option value="">Todos los países</option></select></label>',
    '<label>Provincia<select id="atlasProvince"><option value="">Todas las provincias</option></select></label>',
    '<label>Sector<select id="atlasSector"><option value="">Todos los sectores</option></select></label>',
    '<label>Organización<select id="atlasType"><option value="">Todas</option><option value="Organismo">Organismos / ciencia</option><option value="Empresa">Empresas</option></select></label>',
    '<label>Seguimiento<select id="atlasState"><option value="">Todos</option><option value="pending">Sin contactar / por investigar</option><option value="sent">Contactado / enviado</option><option value="reply">Con respuesta</option><option value="applied">Postulado</option><option value="draft">Borrador</option><option value="other">Otros</option></select></label>',
    '<label>Ordenar<select id="atlasSort"><option value="priority">Prioridad / acciones</option><option value="name">Nombre A–Z</option><option value="province">Provincia A–Z</option><option value="rating">Mi valoración privada</option></select></label>',
    '<button type="button" id="atlasReset" class="control">Limpiar filtros</button></div>',
    '<div class="atlas-geo"><div><h3>Radar por provincias</h3>',
    '<p class="note">Organizaciones identificadas en tu Excel, NO el total provincial. Buenos Aires (provincia) y CABA van por separado.</p>',
    '<p class="atlas-geo-insight" id="atlasUnknownHint">Importá el directorio para revisar cobertura geográfica.</p></div>',
    '<div id="atlasTerritory" class="atlas-territory" aria-label="Seleccionar una provincia de Argentina"></div></div>',
    '<div class="atlas-workspace"><div class="atlas-listpane"><div class="atlas-subhead"><h3>Directorio navegable</h3><span id="atlasVisible" class="micro"></span></div>',
    '<div id="atlasRows" class="atlas-rows"><p class="note">Importá un archivo para navegar el atlas.</p></div>',
    '<button type="button" class="control" id="atlasMore" hidden>Mostrar más</button></div>',
    '<div class="atlas-detailpane"><div class="atlas-subhead"><h3>Ficha / evidencia</h3><span class="micro">NO ES UNA OFERTA ACTIVA</span></div>',
    '<div id="atlasDetail"><p class="note">Elegí una organización para ver su ficha y guardar tu valoración privada.</p></div></div></div>',
    '<details class="atlas-sources"><summary>Fuentes públicas para enriquecer el atlas y analizar empresas, empleo, fondos y proyectos</summary>',
    '<div id="atlasSources" class="atlas-source-list"></div>',
    '<p class="note">Empleados, inversiones y reseñas individuales: sin datos comprobados en las planillas importadas. Los indicadores provinciales NO deben atribuirse a una empresa concreta. Una valoración tuya no es una reseña pública ni evidencia de reputación laboral.</p>',
    '</details>'
  ].join('');
  before.insertAdjacentElement('beforebegin',SECTION);

  const $ = id => SECTION.querySelector('#'+id);
  const norm = value => String(value == null ? '' : value).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/\s+/g,' ').trim();
  const labels = {pending:'Sin contactar',sent:'Enviado / contacto previo',reply:'Con respuesta',applied:'Postulado',draft:'Borrador',other:'Otro'};
  const CACHE = 'opportunity-os-company-atlas-v1';
  const REVIEWS = 'opportunity-os-atlas-personal-notes-v1';
  const safeLink = value => {try {const u=new URL(String(value));return u.protocol==='https:'?u.href:null;}catch{return null;}};
  let records=[],selectedKey='',limit=30,lastImport='',isLoading=false,showAllProvinces=false;
  let personal={};
  try {const x=JSON.parse(localStorage.getItem(REVIEWS)||'{}');if(x&&typeof x==='object'&&!Array.isArray(x))personal=x;}catch{}

  function countryFrom(location) {
    const s=norm(location);
    if(/\bchile\b/.test(s))return 'Chile';
    if(/\bperu\b/.test(s))return 'Perú';
    if(/\bcolombia\b/.test(s))return 'Colombia';
    if(/\bmexico\b/.test(s))return 'México';
    if(/\buruguay\b/.test(s))return 'Uruguay';
    if(/\bbrasil\b|\bbrazil\b/.test(s))return 'Brasil';
    if(/\bbolivia\b/.test(s))return 'Bolivia';
    if(/\becuador\b/.test(s))return 'Ecuador';
    if(/\bespana\b/.test(s))return 'España';
    if(/\bestados unidos\b|\busa\b/.test(s))return 'Estados Unidos';
    if(s==='nacional'||/\bargentina\b/.test(s)||provinceFrom(s))return 'Argentina';
    return 'No informado';
  }
  function provinceFrom(raw) {
    const s=norm(raw);
    if(!s || s==='nacional'||s==='argentina'||/varias provincias|operaciones por provincia/.test(s))return '';
    const special = /\bcaba\b|ciudad autonoma de buenos aires|capital federal/.test(s);
    if(special)return 'CABA';
    if(/\bbs\.?\s?as\b/.test(s))return 'Buenos Aires';
    for(const province of PROVINCES.filter(p=>p!=='CABA')) {
      if(s.includes(norm(province)))return province;
    }
    return '';
  }
  function sectorFrom(value) {
    const s=norm(value);
    if(/mineri|metalifer|geotecni|geolog/.test(s))return 'Minería';
    if(/\bgis\b|\bsig\b|geoespac|geomatic|cartograf|geodat|teledetec/.test(s))return 'Geociencias / GIS';
    if(/energia|petrol|hidrocarb|electri|oleoduct|ypf/.test(s))return 'Energía';
    if(/ambiente|ambiental|clima|forestal|sustentab|recicl|agua/.test(s))return 'Ambiente';
    if(/agric|agro|rural|biologic/.test(s))return 'Agro';
    if(/turism|hotel|hostel|gastronom|restaurant/.test(s))return 'Turismo';
    if(/ciencia|investigac|innovac|vinculac|universid|conicet/.test(s))return 'Innovación / ciencia';
    if(/software|python|datos|backend|tecnolog|ia aplicada|inteligencia artificial|programac|sistemas|it\b/.test(s))return 'Tecnología / datos';
    if(/operacion|gestion|logistic|comercio|venta|administr/.test(s))return 'Gestión / operaciones';
    return 'Otros';
  }
  function stateFrom(raw) {
    const s=norm(raw);
    if(/respuesta|respond|replied|inbound|entrevista|contacto real/.test(s))return 'reply';
    if(/\bapplied\b|postulad|aplicacion enviada/.test(s))return 'applied';
    if(/borrador|\bdraft\b/.test(s))return 'draft';
    if(/enviado|ya enviado|\bsent\b|contacto previo/.test(s))return 'sent';
    if(/rechazad|descartad|rebotad|no interes/.test(s))return 'other';
    return 'pending';
  }
  const stateRank={reply:5,applied:4,sent:3,draft:2,pending:1,other:0};
  function toHeader(row) {return row.map(norm);}
  function getField(row,head,aliases) {
    for(const alias of aliases){const i=head.indexOf(norm(alias));if(i>=0)return String(row[i] == null ? '' : row[i]).trim();}
    return '';
  }
  function asRows(matrix,sheet) {
    if(!Array.isArray(matrix)||!matrix.length)return [];
    const results=[];
    for(let k=0;k<Math.min(10,matrix.length);k++){
      const head=toHeader(matrix[k]||[]);
      let family='';
      if(head.includes('id global')&&head.includes('empresa'))family='companies';
      else if(head.includes('id original')&&head.includes('empresa / entidad'))family='unified';
      else if(head.includes('organismo')&&head.includes('provincia')&&(head.includes('nivel')||head.includes('estado')))family='federal';
      else if(head.includes('empresa')&&head.includes('estado'))family='general';
      if(!family)continue;
      for(let i=k+1;i<Math.min(matrix.length,15000);i++){
        const row=matrix[i]||[];
        const name=getField(row,head,family==='federal'?['organismo']:['empresa / entidad','empresa']);
        if(!name)continue;
        const location=getField(row,head,['provincia','ubicación','ubicacion','localidad']);
        const municipality=getField(row,head,['municipio','localidad']);
        const country=getField(row,head,['país','pais'])||countryFrom(location);
        const province=country==='Argentina'?provinceFrom(location):'';
        const area=getField(row,head,['sector / área','hipótesis / rol','área / dependencia','area','objetivo','sector','tema']);
        const type=(family==='federal'||/secretaria|ministerio|municipalidad|universidad|conicet|instituto nacional|gobierno de|direccion provincial|direccion nacional/.test(norm(name)))?'Organismo':'Empresa';
        const current=getField(row,head,['estado actual / gmail','estado actual','estado']);
        const source=getField(row,head,['sitio / fuente','web fuente','fuente url','fuente']);
        const next=getField(row,head,['próxima acción','accion','acción','objetivo']);
        const priority=getField(row,head,['prioridad']);
        results.push({
          name:name.slice(0,150),key:norm(name)+'|'+norm(country)+(type==='Organismo'?'|'+norm(province)+'|'+norm(municipality):''),
          country:country.slice(0,55),province,municipality:municipality.slice(0,85),type,
          sector:sectorFrom(area+' '+name),area:area.slice(0,200),
          placeText:location.slice(0,100),state:stateFrom(current),stateOriginal:current.slice(0,90),
          action:next.slice(0,230),priority:priority.slice(0,80),
          source:safeLink(source),origin:sheet,
          size:null,funding:null,projects:null
        });
      }
      return results;
    }
    return results;
  }
  // Unificado es el maestro operacional: EMPRESAS_400 incluye filiales y
  // aliases deliberadamente relacionados con registros previos. No importar
  // ambos del mismo libro como si fueran organizaciones independientes.
  function selectWorkbookSheets(sheetNames) {
    const names = Array.isArray(sheetNames) ? sheetNames : [];
    return (names.includes('Unificado') ? ['Unificado'] : ['EMPRESAS_400'])
      .concat('Directorio')
      .filter(name => names.includes(name));
  }
  // Un estado de la hoja maestra conciliada con Gmail no debe ser
  // reemplazado por otro de una hoja editorial anterior, aunque su estado
  // parezca más "avanzado". Esto importa al importar archivos por separado.
  function originAuthority(origin) {
    const names=String(origin||'').split(' · ');
    if(names.includes('Unificado'))return 3;
    if(names.includes('Directorio'))return 2;
    if(names.includes('EMPRESAS_400'))return 1;
    return 0;
  }
  function addRecords(incoming) {
    const merged=new Map(records.map(item=>[item.key,item]));
    incoming.forEach(item=>{
      const old=merged.get(item.key);
      if(!old){merged.set(item.key,item);return;}
      const oldAuthority=originAuthority(old.origin);
      const newAuthority=originAuthority(item.origin);
      const winner=newAuthority===oldAuthority
        ? (stateRank[item.state]>stateRank[old.state]?item:old)
        : (newAuthority>oldAuthority?item:old);
      merged.set(item.key,{
        ...old,
        type:item.type==='Organismo'||old.type==='Organismo'?'Organismo':'Empresa',
        province:old.province||item.province,
        placeText:old.placeText||item.placeText,
        sector:old.sector==='Otros'?item.sector:old.sector,
        area:old.area||item.area,
        state:winner.state,stateOriginal:winner.stateOriginal,
        priority:old.priority||item.priority,
        action:winner.action||old.action||item.action,
        source:old.source||item.source,
        origin:(old.origin||'')+(old.origin===item.origin?'':' · '+item.origin)
      });
    });
    records=[...merged.values()];
  }
  function persist() {
    try {localStorage.setItem(CACHE,JSON.stringify({at:new Date().toISOString(),file:lastImport,records}));return true;}
    catch {return false;}
  }
  let libraryPromise;
  async function excelLibrary() {
    if(window.XLSX)return window.XLSX;
    if(!libraryPromise)libraryPromise=new Promise((resolve,reject)=>{
      const s=document.createElement('script');
      s.src='https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js';
      s.async=true;
      s.onload=()=>window.XLSX?resolve(window.XLSX):reject(new Error('No se pudo inicializar el lector de Excel.'));
      s.onerror=()=>reject(new Error('El lector de Excel no cargó. Probá exportar la hoja a CSV.'));
      document.head.append(s);
    });
    return libraryPromise;
  }
  function csvRows(data) {
    const text=String(data).replace(/^\uFEFF/,'');
    const head=text.split(/\r?\n/,1)[0];
    const sep=head.split(';').length>head.split(',').length?';':',';
    const rows=[];let row=[],field='',quoted=false;
    for(let i=0;i<text.length;i++){
      const c=text[i];
      if(quoted){
        if(c==='"'&&text[i+1]==='"'){field+='"';i++;}
        else if(c==='"')quoted=false;
        else field+=c;
      } else if(c==='"')quoted=true;
      else if(c===sep){row.push(field);field='';}
      else if(c==='\n'){row.push(field.replace(/\r$/,''));rows.push(row);row=[];field='';}
      else field+=c;
    }
    if(row.length||field){row.push(field.replace(/\r$/,''));rows.push(row);}
    return rows;
  }
  async function readFile(file) {
    if(!/\.(xlsx|xls|csv)$/i.test(file.name))throw new Error('Archivo incompatible: necesitás XLSX, XLS o CSV.');
    if(file.size>12*1024*1024)throw new Error('Archivo demasiado grande (máximo 12 MB).');
    if(/\.csv$/i.test(file.name))return asRows(csvRows(await file.text()),file.name);
    const XLSX=await excelLibrary();
    const wb=XLSX.read(new Uint8Array(await file.arrayBuffer()),{type:'array',dense:true});
    const names=selectWorkbookSheets(wb.SheetNames);
    const found=[];
    names.filter(n=>wb.SheetNames.includes(n)).forEach(name=>{
      const matrix=XLSX.utils.sheet_to_json(wb.Sheets[name],{header:1,raw:false,defval:'',blankrows:false});
      found.push(...asRows(matrix,name));
    });
    if(!found.length){
      for(const name of wb.SheetNames.slice(0,15)){
        const matrix=XLSX.utils.sheet_to_json(wb.Sheets[name],{header:1,raw:false,defval:'',blankrows:false});
        const rows=asRows(matrix,name);
        if(rows.length){found.push(...rows);break;}
      }
    }
    return found;
  }
  async function importFiles(files) {
    if(isLoading)return;
    isLoading=true;
    $('atlasUpload').disabled=true;
    const issues=[];
    let added=0;
    try{
      for(const file of files){
        try{
          $('atlasStatus').textContent='Leyendo '+file.name+' dentro del navegador…';
          const parsed=await readFile(file);
          if(!parsed.length){issues.push(file.name+': sin columnas reconocidas');continue;}
          added+=parsed.length;
          addRecords(parsed);
          lastImport=file.name;
        }catch(err){issues.push(file.name+': '+(err.message||'error'));}
      }
      const saved=persist();
      render();
      $('atlasStatus').textContent=(added?records.length+' organizaciones unificadas · '+added+' filas procesadas. ':'No se importaron registros. ')+
        (saved?'Resumen privado guardado en este navegador. ':'No se pudo guardar en el navegador. ')+issues.join(' | ');
    }finally{isLoading=false;$('atlasUpload').disabled=false;}
  }
  const statePriority={reply:0,draft:1,pending:2,applied:3,sent:4,other:5};
  const rv = key=>personal[key]||{};
  function selectOptions(id,options,placeholder) {
    const control=$(id),current=control.value;control.replaceChildren();
    const initial=document.createElement('option');initial.value='';initial.textContent=placeholder;control.append(initial);
    options.forEach(name=>{const op=document.createElement('option');op.value=name;op.textContent=name;control.append(op);});
    control.value=options.includes(current)?current:'';
  }
  function filters() {
    const q=norm($('atlasSearch').value),country=$('atlasCountry').value,
      province=$('atlasProvince').value,sector=$('atlasSector').value,type=$('atlasType').value,
      state=$('atlasState').value;
    return records.filter(r=>
      (!q||norm([r.name,r.area,r.sector,r.country,r.province,r.type,r.action].join(' ')).includes(q)) &&
      (!country||r.country===country)&&(!province||((province==='__UNKNOWN__')?(r.country==='Argentina'&&!r.province):r.province===province))&&
      (!sector||r.sector===sector)&&(!type||r.type===type)&&(!state||r.state===state)
    );
  }
  function sortRows(rows) {
    const order=$('atlasSort').value;
    rows.sort((a,b)=>{
      if(order==='name')return a.name.localeCompare(b.name,'es');
      if(order==='province')return (a.province||'ZZZ').localeCompare(b.province||'ZZZ','es')||a.name.localeCompare(b.name,'es');
      if(order==='rating')return (Number(rv(b.key).stars)||0)-(Number(rv(a.key).stars)||0)||a.name.localeCompare(b.name,'es');
      return (statePriority[a.state]??5)-(statePriority[b.state]??5)||
        (norm(a.priority)==='a'?-1:0)-(norm(b.priority)==='a'?-1:0)||
        a.name.localeCompare(b.name,'es');
    });
  }
  const put=(parent,tag,value,className)=>{
    const x=document.createElement(tag);x.textContent=String(value==null?'':value);
    if(className)x.className=className;parent.append(x);return x;
  };
  function territory(rows){
    const root=$('atlasTerritory');root.replaceChildren();
    const per=new Map(PROVINCES.map(p=>[p,0]));
    rows.forEach(r=>{if(per.has(r.province))per.set(r.province,per.get(r.province)+1);});
    const missing=rows.filter(r=>r.country==='Argentina'&&!r.province).length;
    const sorted=[...per.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0],'es'));
    const max=Math.max(...per.values(),1);
    const focus=new Set(['Buenos Aires','CABA','Córdoba']);
    const spotlight=[...sorted.filter(([name])=>focus.has(name)),...sorted.filter(([name])=>!focus.has(name)&&per.get(name)>0).slice(0,5)];
    const visible=showAllProvinces?sorted:spotlight;
    const hint=$('atlasUnknownHint');
    hint.textContent=records.length?
      missing+' organizaciones argentinas sin provincia identificada · no se les puede atribuir Buenos Aires, CABA ni Córdoba sin evidencia.':
      'Todavía no se cargaron empresas. Usá los enlaces de descubrimiento verificados más abajo.';
    function provinceButton(name,count){
      const b=document.createElement('button');b.type='button';
      b.className='atlas-province'+($('atlasProvince').value===name?' active':'');
      b.style.setProperty('--province-share',Math.max(2,count/max*100).toFixed(1)+'%');
      b.setAttribute('aria-pressed',String($('atlasProvince').value===name));
      put(b,'span',name);put(b,'strong',count);
      b.addEventListener('click',()=>{
        $('atlasProvince').value=$('atlasProvince').value===name?'':name;
        limit=30;render();
      });
      return b;
    }
    visible.forEach(([name,count])=>root.append(provinceButton(name,count)));
    if(rows.length){
      const unknown=document.createElement('button');unknown.type='button';
      unknown.className='atlas-province atlas-province-unknown'+($('atlasProvince').value==='__UNKNOWN__'?' active':'');
      unknown.setAttribute('aria-pressed',String($('atlasProvince').value==='__UNKNOWN__'));
      put(unknown,'span','Argentina · sin provincia');put(unknown,'strong',missing);
      unknown.addEventListener('click',()=>{$('atlasProvince').value=$('atlasProvince').value==='__UNKNOWN__'?'':'__UNKNOWN__';limit=30;render();});
      root.append(unknown);
    }
    if(!showAllProvinces){
      const more=document.createElement('button');more.type='button';more.className='atlas-expand';
      more.textContent='Ver las 24 provincias';
      more.addEventListener('click',()=>{showAllProvinces=true;render();});
      root.append(more);
    } else {
      const fewer=document.createElement('button');fewer.type='button';fewer.className='atlas-expand';
      fewer.textContent='Ver solo las principales';
      fewer.addEventListener('click',()=>{showAllProvinces=false;render();});
      root.append(fewer);
    }
  }
  function drawDetail(record){
    const root=$('atlasDetail');root.replaceChildren();
    if(!record){put(root,'p','Seleccioná una empresa u organismo para revisar su información.','note');return;}
    put(root,'div',record.type+' · '+record.country+(record.province?' / '+record.province:''),'micro');
    put(root,'h4',record.name);
    const grid=put(root,'div','','atlas-facts');
    [['Sector',record.sector],['Ubicación informada',[record.placeText,record.municipality].filter(Boolean).join(' · ')||'No informada'],
     ['Estado de contacto',record.stateOriginal||labels[record.state]],
     ['Prioridad registrada',record.priority||'No informada']].forEach(([key,value])=>{
        const box=put(grid,'div','','atlas-fact');
        put(box,'small',key);put(box,'strong',value);
      });
    if(record.area)put(root,'p','Perfil / área: '+record.area,'atlas-detail-text');
    if(record.action)put(root,'p','Próxima gestión registrada: '+record.action,'atlas-detail-text');
    const missing=put(root,'details','','atlas-missing');
    put(missing,'summary','Datos pendientes de verificar');
    put(missing,'p','Cantidad de empleados, fondos, proyectos y reputación pública: no comprobados para esta organización. No se infieren de estadísticas provinciales.','note');
    put(root,'p','Fuentes de la ficha: '+record.origin+' · Revisar vigencia antes de contactar.','note');
    if(record.source){
      const a=put(root,'a','Abrir fuente guardada ↗','atlas-source-link');
      a.href=record.source;a.target='_blank';a.rel='noopener noreferrer';
    }
    const tools=put(root,'div','','atlas-external');
    [
      ['Buscar posibles vacantes · LinkedIn','https://www.linkedin.com/jobs/search/?keywords='+encodeURIComponent(record.name)+'&location=Argentina'],
      ['Buscar vacantes · Indeed','https://ar.indeed.com/jobs?q='+encodeURIComponent(record.name)+'&l=Argentina'],
      ['Ver perfil de empresa · LinkedIn','https://www.linkedin.com/search/results/companies/?keywords='+encodeURIComponent(record.name)],
      ['Consultar reseñas externas','https://www.google.com/search?q='+encodeURIComponent(record.name+' reseñas empleados opiniones')]
    ].forEach(([label,url])=>{
      const a=put(tools,'a',label+' ↗');a.href=url;a.target='_blank';a.rel='noopener noreferrer';
    });
    const rating=put(root,'div','','atlas-rating');
    put(rating,'p','Mi valoración privada (1–5) · No es reputación pública','note');
    const stars=put(rating,'div','','atlas-stars');
    for(let i=1;i<=5;i++){
      const b=put(stars,'button',(Number(rv(record.key).stars)||0)>=i?'★':'☆');
      b.type='button';b.title=i+' de 5';b.setAttribute('aria-label','Valorar '+i+' de 5');
      b.addEventListener('click',()=>{personal[record.key]={...rv(record.key),stars:i};persistReview();drawDetail(record);drawRows(filters());});
    }
    const label=put(rating,'label','Nota privada (se guarda solo en este navegador)');
    const note=document.createElement('textarea');note.maxLength=700;note.rows=3;note.value=rv(record.key).note||'';
    label.append(note);
    note.addEventListener('change',()=>{personal[record.key]={...rv(record.key),note:note.value.slice(0,700)};persistReview();});
  }
  function persistReview(){try{localStorage.setItem(REVIEWS,JSON.stringify(personal));}catch{}}
  function drawRows(rows){
    const list=$('atlasRows');list.replaceChildren();
    $('atlasVisible').textContent=rows.length+' de '+records.length;
    if(!rows.length){put(list,'p',records.length?'No hay coincidencias. Probá quitar filtros.':'Cargá un Excel para empezar.','note');$('atlasMore').hidden=true;return;}
    rows.slice(0,limit).forEach(r=>{
      const b=document.createElement('button');b.type='button';b.className='atlas-row'+(r.key===selectedKey?' active':'');
      put(b,'strong',r.name);
      put(b,'small',[r.country,r.province,r.sector].filter(Boolean).join(' · '));
      const foot=put(b,'span','','atlas-row-foot');
      put(foot,'span',labels[r.state]||'Sin estado');
      if(rv(r.key).stars)put(foot,'span','★ '+rv(r.key).stars+'/5');
      b.addEventListener('click',()=>{selectedKey=r.key;drawRows(rows);drawDetail(r);});
      list.append(b);
    });
    $('atlasMore').hidden=rows.length<=limit;
    $('atlasMore').textContent='Mostrar más · '+Math.min(rows.length-limit,30);
  }
  function render(){
    $('atlasErase').hidden=!records.length;
    const countries=[...new Set(records.map(r=>r.country).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'es'));
    selectOptions('atlasCountry',countries,'Todos los países');
    selectOptions('atlasProvince',[...PROVINCES,'__UNKNOWN__'],'Todas las provincias');
    const noProv=$('atlasProvince').querySelector('option[value="__UNKNOWN__"]');if(noProv)noProv.textContent='Sin provincia informada';
    selectOptions('atlasSector',SECTORS,'Todos los sectores');
    $('atlasCount').textContent=String(records.length||'—');
    $('atlasKnown').textContent=String(records.filter(r=>r.province).length||0);
    $('atlasAgencies').textContent=String(records.filter(r=>r.type==='Organismo').length||0);
    $('atlasMoved').textContent=String(records.filter(r=>['sent','reply','applied'].includes(r.state)).length||0);
    // La barra territorial refleja país/sector/tipo/estado/búsqueda,
    // pero NO aplica el filtro de provincia, para permitir cambiarla.
    const chosenProvince=$('atlasProvince').value;
    $('atlasProvince').value='';
    const withoutProvince=filters();
    $('atlasProvince').value=chosenProvince;
    territory(withoutProvince);
    const result=filters();sortRows(result);
    drawRows(result);
    const current=records.find(r=>r.key===selectedKey);
    drawDetail(current||null);
    window.dispatchEvent(new CustomEvent('opportunity:atlas-change'));
  }
  $('atlasUpload').addEventListener('click',()=>$('atlasFiles').click());
  $('atlasFiles').addEventListener('change',async event=>{
    const files=[...(event.target.files||[])];
    if(files.length)await importFiles(files);
    event.target.value='';
  });
  window.addEventListener('opportunity:local-file',async event=>{
    if(event.detail&&event.detail.file)await importFiles([event.detail.file]);
  });
  $('atlasErase').addEventListener('click',()=>{
    records=[];selectedKey='';personal={};
    try{localStorage.removeItem(CACHE);localStorage.removeItem(REVIEWS);}catch{}
    $('atlasStatus').textContent='Atlas local borrado en este navegador. Los archivos originales no se modificaron.';
    render();
  });
  ['atlasSearch','atlasCountry','atlasProvince','atlasSector','atlasType','atlasState','atlasSort']
    .forEach(id=>$(id).addEventListener('input',()=>{limit=30;render();}));
  $('atlasReset').addEventListener('click',()=>{
    ['atlasSearch','atlasCountry','atlasProvince','atlasSector','atlasType','atlasState'].forEach(id=>$(id).value='');
    $('atlasSort').value='priority';limit=30;render();
  });
  $('atlasMore').addEventListener('click',()=>{limit+=30;render();});
  const sources=$('atlasSources');
  OFFICIAL.forEach(([label,url,note])=>{
    const box=put(sources,'div','','atlas-public-source');
    const a=put(box,'a',label+' ↗');a.href=url;a.target='_blank';a.rel='noopener noreferrer';
    put(box,'p',note,'note');
  });
  try {
    const saved=JSON.parse(localStorage.getItem(CACHE)||'null');
    if(saved&&Array.isArray(saved.records)&&saved.records.length<=20000){
      records=saved.records.filter(x=>x&&typeof x.key==='string'&&typeof x.name==='string');
      lastImport=saved.file||'archivo anterior';
      $('atlasStatus').textContent=records.length+' organizaciones cargadas desde la copia privada del navegador ('+lastImport+').';
    }
  }catch{}
  render();
})();
