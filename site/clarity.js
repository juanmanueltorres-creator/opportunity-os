/* Opportunity OS / claridad: rutas de búsqueda y empresas verificadas para investigar.
   Fuente pública separada de los registros privados. No se envían postulaciones ni contactos. */
(() => {
  'use strict';
  const atlas=document.querySelector('#atlas-empresas');
  const quick=document.querySelector('.quick-panel');
  if(!atlas||!quick)return;
  const norm=v=>String(v==null?'':v).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim();
  const jobsBase='https://www.linkedin.com/jobs/search/?';
  const indeedBase='https://ar.indeed.com/jobs?';
  const paths=[
    {name:'Todo el país',where:'Argentina',word:'GIS OR Python OR soporte técnico',value:'ALL',desc:'Sin provincia preseleccionada. Primero evaluá puesto, idioma, modalidad y elegibilidad.'},
    {name:'Buenos Aires',where:'Buenos Aires, Provincia de Buenos Aires, Argentina',word:'GIS OR soporte técnico OR analista de datos',value:'BA',desc:'Provincia de Buenos Aires (no incluye CABA).'},
    {name:'CABA',where:'Ciudad Autónoma de Buenos Aires, Argentina',word:'soporte de aplicaciones OR Python OR GIS',value:'CABA',desc:'Ciudad Autónoma de Buenos Aires; se analiza aparte de PBA.'},
    {name:'Remoto',where:'Argentina',word:'Python OR soporte técnico OR SIG',value:'REMOTE',desc:'Remoto es una modalidad de aviso, no un domicilio de empresa. Verificá elegibilidad desde Argentina e idioma laboral.'},
    {name:'Córdoba',where:'Córdoba, Argentina',word:'GIS OR soporte OR operaciones',value:'CBA',desc:'Oportunidades presenciales o híbridas y búsqueda local.'}
  ];
  const compact=document.createElement('nav');
  compact.className='clarity-nav';
  compact.setAttribute('aria-label','Atajos de Opportunity OS');
  compact.innerHTML=[
    '<span class="micro">IR A</span>',
    '<a href="#quickTitle">Buscar trabajo</a>',
    '<a href="#atlas-empresas">Mis empresas</a>',
    '<a href="#discovery-targets">Ampliar directorio</a>',
    '<a href="#contexto-productivo">Datos por provincia</a>',
    '<a href="#cards">Vacantes</a>'
  ].join('');
  quick.insertAdjacentElement('beforebegin',compact);

  const territoryBox=document.createElement('section');
  territoryBox.className='clarity-routes';
  territoryBox.setAttribute('aria-labelledby','routeHeading');
  territoryBox.innerHTML=[
    '<div class="clarity-routes-head"><div><span class="micro eyebrow">EMPEZAR POR DESTINO / ACCIÓN</span>',
    '<h2 id="routeHeading">¿Dónde buscamos hoy?</h2></div><p class="note">Búsquedas externas, no vacantes confirmadas. Elegí una zona y abrí el portal; no se lanzan varias pestañas solas.</p></div>',
    '<div class="clarity-route-tabs" id="routeTabs" role="group" aria-label="Regiones y modalidad"></div>',
    '<div class="clarity-route-result"><span id="routeDescription" class="note"></span>',
    '<div class="clarity-route-links" id="routeLinks"></div></div>'
  ].join('');
  quick.insertAdjacentElement('afterend',territoryBox);
  const routeTabs=territoryBox.querySelector('#routeTabs');
  const routeLinks=territoryBox.querySelector('#routeLinks');
  const routeText=territoryBox.querySelector('#routeDescription');
  let active=0;
  const addLink=(root,label,url,cls)=>{
    const a=document.createElement('a');a.href=url;a.textContent=label+' ↗';
    a.target='_blank';a.rel='noopener noreferrer';
    if(cls)a.className=cls;
    root.append(a);return a;
  };
  function updateRoutes(){
    routeTabs.replaceChildren();routeLinks.replaceChildren();
    paths.forEach((path,i)=>{
      const b=document.createElement('button');b.type='button';b.textContent=path.name;
      b.className='clarity-destination'+(i===active?' active':'');
      b.setAttribute('aria-pressed',String(i===active));
      b.addEventListener('click',()=>{active=i;updateRoutes();});
      routeTabs.append(b);
    });
    const path=paths[active];
    routeText.textContent=path.desc;
    const params=new URLSearchParams({keywords:path.word,location:path.where});
    if(path.value==='REMOTE')params.set('f_WT','2');
    addLink(routeLinks,'LinkedIn · empleos',jobsBase+params.toString(),'clarity-primary-link');
    const indeedParams=new URLSearchParams({q:path.word,l:path.where});
    addLink(routeLinks,'Indeed',indeedBase+indeedParams.toString());
    if(path.value==='REMOTE'){
      addLink(routeLinks,'Workana · proyectos','https://www.workana.com/es/jobs?query='+encodeURIComponent('Python Excel automatización'));
      addLink(routeLinks,'Get on Board','https://www.getonbrd.com/jobs');
    }else if(path.value==='BA'||path.value==='CABA'){
      addLink(routeLinks,'Directorio CESSI','https://cessi.org.ar/directorio-de-empresas/');
    }
  }
  updateRoutes();

  const workspace=atlas.querySelector('.atlas-workspace');
  if(!workspace)return;
  const discover=document.createElement('section');
  discover.id='discovery-targets';
  discover.className='discovery-targets';
  discover.setAttribute('aria-labelledby','discoveryTitle');
  discover.innerHTML=[
    '<div class="discovery-heading"><div><span class="micro eyebrow">EXPLORACIÓN / FUENTES PÚBLICAS</span>',
    '<h3 id="discoveryTitle">Más empresas para investigar</h3>',
    '<p class="note">Fichas con ubicación y actividad publicadas por CESSI. No son avisos abiertos, y su domicilio no demuestra contratación remota. Tu Excel no se modifica.</p></div>',
    '<a href="https://cessi.org.ar/directorio-de-empresas/" target="_blank" rel="noopener noreferrer">Ver directorio completo ↗</a></div>',
    '<div class="discovery-controls"><div id="discoveryRegions" role="group" aria-label="Explorar empresas por provincia"></div>',
    '<label>Buscar en la selección <input type="search" id="discoverySearch" placeholder="Software, datos, IoT, empresa…" autocomplete="off"></label></div>',
    '<div class="discovery-count" id="discoveryCount" role="status" aria-live="polite">Cargando empresas verificables…</div>',
    '<div class="discovery-list" id="discoveryList"></div>',
    '<button type="button" class="control" id="discoveryMore" hidden>Ver más empresas</button>',
    '<p class="note discovery-foot">Fecha de consulta: 04/11/2026 · Domicilio declarado en CESSI. Verificá puesto, idioma y modalidad antes de postular. Estos registros NO se suman al contador de empresas de tu Excel.</p>'
  ].join('');
  workspace.insertAdjacentElement('afterend',discover);
  const $=id=>discover.querySelector('#'+id);
  let catalog=[],region='Buenos Aires',visible=6,err=false;
  function loadedNames(){
    try{
      const parsed=JSON.parse(localStorage.getItem('opportunity-os-company-atlas-v1')||'null');
      return new Set((parsed?.records||[]).map(r=>norm(r.name)));
    }catch{return new Set();}
  }
  function card(x,have){
    const row=document.createElement('article');row.className='discovery-card';
    const top=document.createElement('div');top.className='discovery-card-top';
    const left=document.createElement('div');left.className='discovery-card-title';
    const title=document.createElement('h4');title.textContent=x.name;left.append(title);
    const small=document.createElement('p');small.textContent=x.city+' · '+x.province+' · '+x.activity;left.append(small);
    top.append(left);
    const flag=document.createElement('span');flag.className='discovery-flag';
    flag.textContent=have.has(norm(x.name))?'Ya figura en tu Excel':'Objetivo para investigar';
    top.append(flag);row.append(top);
    const actions=document.createElement('div');actions.className='discovery-card-links';
    addLink(actions,'Fuente CESSI',x.source_url);
    const jp=new URLSearchParams({keywords:x.name,location:'Argentina'});
    addLink(actions,'Buscar vacantes',jobsBase+jp.toString(),'clarity-primary-link');
    row.append(actions);
    return row;
  }
  function render(){
    const chosen=catalog.filter(x=>
      (region==='Todas'||(region==='Interior'?x.province!=='Buenos Aires'&&x.province!=='CABA':x.province===region)) &&
      (!norm($('discoverySearch').value)||norm([x.name,x.city,x.province,x.activity].join(' ')).includes(norm($('discoverySearch').value)))
    );
    const counts=new Map();
    for(const x of catalog)counts.set(x.province,(counts.get(x.province)||0)+1);
    const regions=[['Buenos Aires','PBA'],['CABA','CABA'],['Interior','Otras provincias'],['Todas','Todas']];
    const roots=$('discoveryRegions');roots.replaceChildren();
    regions.forEach(([value,label])=>{
      const btn=document.createElement('button');btn.type='button';btn.className='discovery-filter'+(region===value?' active':'');
      btn.textContent=label+(value==='Buenos Aires'||value==='CABA'?' · '+(counts.get(value)||0):'');
      btn.setAttribute('aria-pressed',String(region===value));
      btn.addEventListener('click',()=>{region=value;visible=6;render();});
      roots.append(btn);
    });
    const list=$('discoveryList');list.replaceChildren();
    const known=loadedNames();
    chosen.slice(0,visible).forEach(x=>list.append(card(x,known)));
    $('discoveryCount').textContent=chosen.length+' empresas con fuente y domicilio · mostrando '+Math.min(visible,chosen.length);
    $('discoveryMore').hidden=chosen.length<=visible;
    if(err)$('discoveryCount').textContent='No fue posible cargar el directorio de referencia. Consultá CESSI directamente.';
  }
  $('discoverySearch').addEventListener('input',()=>{visible=6;render();});
  $('discoveryMore').addEventListener('click',()=>{visible+=6;render();});
  window.addEventListener('opportunity:atlas-change',()=>render());
  async function load(){
    try{
      const res=await fetch('/discovery-companies-2026.json',{cache:'force-cache'});
      if(!res.ok)throw new Error('HTTP '+res.status);
      const data=await res.json();
      if(data.schema_version!==1||!Array.isArray(data.companies)||data.companies.length<20||data.companies.length>150)throw new Error('Fuente inesperada');
      const names=new Set();
      for(const x of data.companies){
        if(typeof x.name!=='string'||x.name.length<2||
          typeof x.province!=='string'||typeof x.city!=='string'||
          typeof x.activity!=='string'||!/^https:\/\/cessi\.org\.ar\/directorio-de-empresas\/(\?pagina=\d+)?$/.test(x.source_url)||
          names.has(norm(x.name)))throw new Error('Ficha inválida o duplicada');
        names.add(norm(x.name));
      }
      catalog=data.companies;
    }catch(e){err=true;}
    render();
  }
  load();
})();
