/* Public market learning + curated national/international companies + opt-in Leaflet map.
   Public datasets only. Markers are regional aggregates, never company geocodes. */
(() => {
  'use strict';
  const territory=document.querySelector('.territory');
  const discovery=document.getElementById('discovery-targets');
  if(!territory||!discovery)return;
  const node=(name,cls,content)=>{const x=document.createElement(name);if(cls)x.className=cls;if(content!=null)x.textContent=content;return x;};
  const link=(name,href)=>{let u;try{u=new URL(href);}catch{return null;}if(u.protocol!=='https:')return null;const a=node('a','',name);a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';return a;};
  const norm=x=>String(x||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const fmt=n=>new Intl.NumberFormat('es-AR',{maximumFractionDigits:0}).format(n);
  const edu=node('section','market-learning');
  edu.id='mercado-laboral';
  edu.setAttribute('aria-labelledby','marketLearningTitle');
  edu.innerHTML=[
    '<div class="market-heading"><span class="micro eyebrow">ESTRUCTURA LABORAL · DATOS VERIFICADOS</span>',
    '<h2 id="marketLearningTitle">¿Dónde hay más oportunidades?</h2>',
    '<p class="note">Una empresa no es una vacante, un trabajador no es una postulación y un sector grande no garantiza empleo remoto. Compará tamaño de mercado, tipos de puestos y barreras de entrada.</p></div>',
    '<div class="market-figures" id="marketFigures">Cargando datos con fuentes…</div>',
    '<p id="marketPeriodCaveat" class="market-warning"></p>',
    '<div class="market-comparison" id="marketComparison"></div>',
    '<div class="market-questions"><h3>Antes de elegir un sector</h3><div id="marketQuestions"></div></div>',
    '<details class="market-sources"><summary>Fuentes y metodología</summary><div id="marketSources"></div></details>'
  ].join('');
  territory.insertAdjacentElement('beforebegin',edu);
  const $=id=>edu.querySelector('#'+id);

  const guide=node('section','public-company-guide');
  guide.id='empresas-publicas';
  guide.setAttribute('aria-labelledby','publicCompanyTitle');
  guide.innerHTML=[
    '<div class="public-company-heading"><div><span class="micro eyebrow">ARGENTINA + LATAM + INTERNACIONAL</span>',
    '<h3 id="publicCompanyTitle">Empresas para investigar, no solo vacantes</h3>',
    '<p class="note">Listado editorial con portales oficiales: no demuestra contratación actual, modalidad ni elegibilidad desde Argentina. Comparalo con los avisos del radar.</p></div>',
    '<span id="publicCompanyCount" class="public-company-count"></span></div>',
    '<div class="public-company-controls"><label>Buscar empresa o sector<input id="publicCompanySearch" type="search" placeholder="GIS, operaciones, agro, soporte…"></label>',
    '<label>Alcance<select id="publicCompanyRegion"><option value="all">Todas las regiones</option><option value="arg">Argentina</option><option value="latam">Latinoamérica</option><option value="global">Internacional</option></select></label></div>',
    '<div id="publicCompanyList" class="public-company-list">Cargando fuentes…</div>',
    '<button type="button" class="control" id="publicCompanyMore" hidden>Mostrar más empresas</button>',
    '<div class="public-map-entry"><div><h4>Mapa de la cobertura del directorio</h4>',
    '<p class="note">Puntos agrupados por provincia o región de referencia. No son coordenadas de oficinas ni mapas de vacantes. La cobertura es una muestra editorial, no un censo.</p></div>',
    '<button type="button" class="control" id="publicMapLoad">Abrir mapa Leaflet</button></div>',
    '<p class="public-map-privacy">El mapa se carga solo si lo abrís. Usa Leaflet y teselas de OpenStreetMap, que reciben una solicitud desde tu navegador.</p>',
    '<div id="publicMap" class="public-map" hidden aria-label="Mapa agregado de empresas y fuentes"></div>',
    '<p id="publicMapStatus" class="note" role="status"></p>'
  ].join('');
  discovery.insertAdjacentElement('afterbegin',guide);
  const g=id=>guide.querySelector('#'+id);
  let items=[],companiesCessi=[],map=null;
  let current=6;
  const area=id=>String(id||'').toLowerCase();
  function regionLabel(place){
    if(place==='Argentina')return 'arg';
    if(/LATAM|Sudam.rica|Colombia|Ecuador|Panam/i.test(place))return 'latam';
    return 'global';
  }
  function renderCompanies(){
    const q=norm(g('publicCompanySearch').value).trim(),reg=g('publicCompanyRegion').value;
    const chosen=items.filter(i=>(reg==='all'||regionLabel(i.region)===reg)&&(!q||norm([i.name,i.sector,i.search_scope,i.region].join(' ')).includes(q)));
    g('publicCompanyCount').textContent=chosen.length+' rutas editoriales';
    const list=g('publicCompanyList');list.replaceChildren();
    chosen.slice(0,current).forEach(c=>{
      const article=node('article','public-company-row');
      const meta=node('div','public-company-meta');
      meta.append(node('span','micro',c.region+' · '+c.sector),node('h4','',c.name),node('p','',c.search_scope));
      const note=node('p','public-company-caution',c.caution);
      const a=link('Consultar sitio oficial',c.careers_url);
      article.append(meta,note);if(a)article.append(a);list.append(article);
    });
    if(!chosen.length)list.append(node('p','note','No hay coincidencias. Probá otro sector o región.'));
    g('publicCompanyMore').hidden=chosen.length<=current;
  }
  g('publicCompanySearch').addEventListener('input',()=>{current=6;renderCompanies();});
  g('publicCompanyRegion').addEventListener('change',()=>{current=6;renderCompanies();});
  g('publicCompanyMore').addEventListener('click',()=>{current+=8;renderCompanies();});

  const CENTERS={
    'Buenos Aires':[-37.1,-59.5],'CABA':[-34.61,-58.38],
    'Córdoba':[-31.4,-64.2],'Santa Fe':[-31.6,-60.7],
    'Tucumán':[-26.8,-65.2],'Mendoza':[-32.9,-68.85],
    'Río Negro':[-40.8,-63],'San Juan':[-31.53,-68.52],
    'Argentina':[-38,-63],'Sudamérica':[-12,-58],
    'LATAM':[4,-79],'Colombia / Ecuador / Panamá':[3,-75],
    'Internacional':[31,-15]
  };
  function mapGroups(){
    const groups=new Map();
    for(const c of companiesCessi){
      if(!CENTERS[c.province])continue;
      const k=c.province;groups.set(k,(groups.get(k)||0)+1);
    }
    for(const c of items){
      let k=c.region;
      if(!CENTERS[k])k='LATAM';
      groups.set(k,(groups.get(k)||0)+1);
    }
    return [...groups].filter(([k])=>CENTERS[k]);
  }
  function initMap(){
    if(!window.L)throw Error('No se encontró Leaflet.');
    const host=g('publicMap');host.hidden=false;
    map=window.L.map(host,{scrollWheelZoom:false,minZoom:2,maxZoom:9}).setView([-23,-63],3);
    window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{
      maxZoom:9,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    for(const [place,count] of mapGroups()){
      const mark=window.L.circleMarker(CENTERS[place],{
        radius:Math.min(22,8+Math.sqrt(count)*3),color:'#c9eda0',fillColor:'#799c61',
        fillOpacity:.6,weight:2
      }).addTo(map);
      const label=node('div','');
      label.append(node('strong','',place),node('p','',count+' fichas de la selección pública. Ubicación regional aproximada; no es una vacante ni sede geocodificada.'));
      mark.bindPopup(label);
    }
    map.invalidateSize();
    g('publicMapStatus').textContent=mapGroups().length+' agrupaciones regionales representadas. Fuente: CESSI y portales oficiales; no es el universo de empresas.';
  }
  g('publicMapLoad').addEventListener('click',()=>{
    const button=g('publicMapLoad');
    if(map){
      const hidden=!g('publicMap').hidden;
      g('publicMap').hidden=hidden;button.textContent=hidden?'Mostrar mapa':'Ocultar mapa';
      if(!hidden)setTimeout(()=>map.invalidateSize(),20);
      return;
    }
    button.disabled=true;button.textContent='Cargando mapa…';
    const load=()=>new Promise((resolve,reject)=>{
      if(window.L){resolve();return;}
      const css=document.createElement('link');css.rel='stylesheet';
      css.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      document.head.append(css);
      const script=document.createElement('script');
      script.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
      script.onload=resolve;script.onerror=()=>reject(Error('No se pudo cargar Leaflet.'));
      document.head.append(script);
    });
    load().then(()=>{initMap();button.textContent='Ocultar mapa';}).catch(e=>{
      g('publicMapStatus').textContent=e.message+' El directorio y los datos siguen disponibles.';
      button.textContent='Reintentar mapa';
    }).finally(()=>{button.disabled=false;});
  });
  document.addEventListener('opportunity:workspace-view',event=>{
    if(event.detail?.view==='empresas'&&map&&!g('publicMap').hidden)setTimeout(()=>map.invalidateSize(),100);
  });
  function renderMarket(data){
    const figures=$('marketFigures');figures.replaceChildren();
    data.figures.forEach(f=>{
      const x=node('article','market-figure');
      const num=node('strong','',fmt(f.value));
      x.append(node('span','micro',f.label),num,node('p','',f.unit),node('small','',f.scope+' · '+f.period));
      const a=link('Ver fuente',f.source_url);if(a)x.append(a);
      figures.append(x);
    });
    $('marketPeriodCaveat').textContent=data.scope_note;
    const compare=$('marketComparison');compare.replaceChildren();
    data.comparison.forEach(c=>{
      const card=node('article','market-path');
      card.append(node('span','micro',c.level),node('h3','',c.label),node('p','',c.possibilities),
       node('p','market-tradeoff',c.tradeoff),node('strong','market-route',c.route));
      const search=node('button','control','Explorar esta vía');
      search.type='button';
      search.addEventListener('click',()=>{
        const mapped={commerce:{track:'management_operations',query:''},mining:{track:'gis_geoscience',query:''},
          software:{track:'software_ai',query:''},freelance:null}[c.id];
        if(c.id==='freelance')document.dispatchEvent(new CustomEvent('opportunity:workspace-go',{detail:{view:'empresas',goal:'freelance'}}));
        else if(mapped)document.dispatchEvent(new CustomEvent('opportunity:workspace-go',{detail:{view:'buscar',...mapped,mode:'REMOTE'}}));
      });
      card.append(search);compare.append(card);
    });
    const qs=$('marketQuestions');qs.replaceChildren();
    data.questions.forEach(question=>qs.append(node('p','',question)));
    const sources=$('marketSources');sources.replaceChildren();
    data.sources.forEach(x=>{const a=link(x.label,x.url);if(a)sources.append(a);});
  }
  (async()=>{
    const files=['market-context-2026.json','public-company-guides-2026.json','discovery-companies-2026.json'];
    const results=await Promise.all(files.map(name=>fetch('/'+name,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(name);return r.json();})));
    const [market,curated,cessi]=results;
    if(market.schema_version!==1||curated.schema_version!==1||cessi.schema_version!==1||
      !Array.isArray(market.figures)||!Array.isArray(curated.targets)||!Array.isArray(cessi.companies))throw Error('Formato inesperado');
    items=curated.targets;companiesCessi=cessi.companies;
    renderMarket(market);renderCompanies();
    g('publicMapStatus').textContent='Mapa opcional · no se descarga hasta que lo abras.';
  })().catch(()=>{
    $('marketFigures').textContent='No se cargaron los indicadores. Consultá directamente OEDE y SIACAM.';
    g('publicCompanyList').textContent='No pudimos cargar el directorio editorial.';
  });
})();
