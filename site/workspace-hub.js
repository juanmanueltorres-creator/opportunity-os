/* Opportunity OS — single workspace navigation over existing modules.
   No state migrations, no duplicate data ingestion, no backend changes. */
(() => {
  'use strict';
  const nav=document.querySelector('.clarity-nav');
  const orientation=document.querySelector('.orientation-guide');
  const quick=document.querySelector('.quick-panel');
  const routes=document.querySelector('.clarity-routes');
  const atlas=document.querySelector('#atlas-empresas');
  const discovery=document.querySelector('#discovery-targets');
  const tracker=document.querySelector('.tracker-panel');
  const cep=document.querySelector('#contexto-productivo');
  const today=document.querySelector('.today');
  const vacancies=document.querySelector('.layout');
  const statrow=document.querySelector('.statrow');
  const territorial=document.querySelector('.territory');
  const sources=document.querySelector('.sources');
  if(!nav||!orientation||!quick||!routes||!atlas||!discovery||!tracker||!cep||!today||!vacancies) return;
  // Show one search surface: specialty + region, not two competing large panels.
  const chips=quick.querySelector('#quickChips');
  if(chips){
    routes.classList.add('hub-inline-routes');
    chips.insertAdjacentElement('afterend',routes);
  }
  const companySwitch=document.createElement('div');
  companySwitch.className='hub-company-switch';
  companySwitch.setAttribute('role','group');
  companySwitch.setAttribute('aria-label','Elegir qué empresas explorar');
  const companyChoices=[
    ['private','Mi directorio · Excel'],
    ['discovery','Descubrir empresas · fuentes públicas']
  ];
  const companyHint=document.createElement('p');
  companyHint.className='note hub-company-hint';
  let companyMode='discovery';
  try{
    const stored=JSON.parse(localStorage.getItem('opportunity-os-company-atlas-v1')||'null');
    if(Array.isArray(stored?.records)&&stored.records.length)companyMode='private';
  }catch{}
  if(location.hash==='#discovery-targets')companyMode='discovery';
  if(location.hash==='#atlas-empresas')companyMode='private';
  companyChoices.forEach(([key,label])=>{
    const button=document.createElement('button');button.type='button';
    button.dataset.companyView=key;button.className='hub-company-option';button.textContent=label;
    button.addEventListener('click',()=>{companyMode=key;switchCompanies();});
    companySwitch.append(button);
  });
  companySwitch.append(companyHint);
  atlas.insertAdjacentElement('beforebegin',companySwitch);
  function switchCompanies(){
    if(current!=='empresas')return;
    atlas.hidden=companyMode!=='private';
    discovery.hidden=companyMode!=='discovery';
    companySwitch.querySelectorAll('button').forEach(button=>{
      const selected=button.dataset.companyView===companyMode;
      button.classList.toggle('active',selected);
      button.setAttribute('aria-pressed',String(selected));
    });
    companyHint.textContent=companyMode==='private'?
      'Estos registros vienen de tu Excel, no del directorio público. Importá cuando necesites actualizar.':
      'Estas fichas tienen fuente pública, pero no confirman vacantes ni se añaden a tu seguimiento.';
  }
  const VIEWS={
    orientacion:{label:'Orientarme',hint:'Un punto de partida público: elegí un objetivo, un área y tu modalidad. No requiere Excel.',sections:[orientation]},
    buscar:{label:'Buscar trabajo',hint:'Vacantes verificables y búsquedas directas, priorizando oportunidades en español.',sections:[quick,routes,statrow,today,vacancies]},
    empresas:{label:'Empresas',hint:'Organizaciones y organismos de tu directorio, más objetivos públicos para investigar.',sections:[companySwitch,atlas,discovery]},
    seguimiento:{label:'Seguimiento',hint:'Tus postulaciones y contactos, sin duplicar ni publicar el Excel.',sections:[tracker]},
    datos:{label:'Datos y fuentes',hint:'Indicadores territoriales oficiales y trazabilidad de las fuentes. No son vacantes.',sections:[cep,territorial,sources]}
  };
  // CEP is rendered by its own module inside atlas. Move the element,
  // retaining all existing event listeners and its pointers to atlas filters.
  atlas.insertAdjacentElement('afterend',cep);

  const parent=nav.parentElement;
  const top=document.createElement('div');
  top.className='workspace-hub';
  top.id='workspace-hub';
  top.innerHTML=[
    '<div class="hub-heading"><div><span class="micro eyebrow">OPPORTUNITY OS / ESPACIO DE TRABAJO</span>',
    '<h2>Una sola vista para decidir qué hacer.</h2>',
    '<p id="hubHint" class="note"></p></div>',
    '<div class="hub-action"><button id="hubImport" class="control primary" type="button">Importar mi Excel</button>',
    '<span>Actualiza seguimiento y atlas en este navegador.</span></div></div>',
    '<div id="hubTabs" class="hub-tabs" role="tablist" aria-label="Secciones de Opportunity OS"></div>'
  ].join('');
  parent.insertBefore(top,nav);
  nav.remove();
  const tabs=top.querySelector('#hubTabs'),hint=top.querySelector('#hubHint');
  let current=null;

  function statusMessage(){
    const t=tracker.querySelector('#trackerTotal')?.textContent?.trim();
    const a=atlas.querySelector('#atlasCount')?.textContent?.trim();
    const has=t&&t!=='—'&&t!=='0';
    const hasAtlas=a&&a!=='—'&&a!=='0';
    return has||hasAtlas?'Tus datos locales siguen disponibles; no hace falta volver a importar.':'Importá tu planilla cuando quieras consultar el seguimiento y las empresas.';
  }
  function choose(view,{scroll=true,replace=false}={}){
    if(!Object.prototype.hasOwnProperty.call(VIEWS,view))view='buscar';
    current=view;
    for(const [id,config] of Object.entries(VIEWS)){
      for(const section of config.sections)if(section)section.hidden=id!==view;
    }
    if(view==='empresas')switchCompanies();
    top.querySelector('.hub-action').hidden=view!=='seguimiento';
    hint.textContent=VIEWS[view].hint+(view==='seguimiento'?' '+statusMessage():'');
    tabs.querySelectorAll('[data-view]').forEach(button=>{
      const selected=button.dataset.view===view;
      button.setAttribute('aria-selected',String(selected));
      button.tabIndex=selected?0:-1;
      button.classList.toggle('active',selected);
    });
    const hash='#'+view;
    if(replace)history.replaceState(null,'',hash);
    else if(location.hash!==hash)history.pushState(null,'',hash);
    if(scroll)top.scrollIntoView({behavior:'auto',block:'start'});
    document.dispatchEvent(new CustomEvent('opportunity:workspace-view',{detail:{view}}));
  }
  const icons={orientacion:'01',buscar:'02',empresas:'03',seguimiento:'04',datos:'05'};
  for(const [id,{label}] of Object.entries(VIEWS)){
    const button=document.createElement('button');
    button.type='button';button.role='tab';button.dataset.view=id;
    button.className='hub-tab';
    const num=document.createElement('span');num.className='hub-tab-num';num.textContent=icons[id];
    const title=document.createElement('strong');title.textContent=label;
    button.append(num,title);
    button.addEventListener('click',()=>choose(id));
    button.addEventListener('keydown',e=>{
      if(!['ArrowRight','ArrowLeft','Home','End'].includes(e.key))return;
      e.preventDefault();
      const ids=Object.keys(VIEWS),i=ids.indexOf(current);
      let next;
      if(e.key==='Home')next=ids[0];
      else if(e.key==='End')next=ids[ids.length-1];
      else next=ids[(i+ids.length+(e.key==='ArrowRight'?1:-1))%ids.length];
      choose(next);tabs.querySelector('[data-view="'+next+'"]')?.focus();
    });
    tabs.append(button);
  }

  // Keep quick portal links and one explicit location choice synchronized.
  const locationNames={
    'Todo el país':'Argentina',
    'Buenos Aires':'Provincia de Buenos Aires, Argentina',
    'CABA':'Ciudad Autónoma de Buenos Aires, Argentina',
    'Córdoba':'Córdoba, Argentina',
    'Remoto':'Argentina'
  };
  const quickLinks=quick.querySelector('#quickPortalLinks');
  const regionTabs=routes.querySelector('#routeTabs');
  const chosenArea=()=>[...(regionTabs?.querySelectorAll('button')||[])].find(x=>x.getAttribute('aria-pressed')==='true')?.textContent?.trim()||'Todo el país';
  function updatePortalRegion(){
    const choice=chosenArea();
    quickLinks?.querySelectorAll('a[href]').forEach(link=>{
      let u;try{u=new URL(link.href);}catch{return;}
      if(u.hostname==='www.linkedin.com'&&u.pathname.startsWith('/jobs/search')){
        u.searchParams.set('location',locationNames[choice]||'Argentina');
        if(choice==='Remoto')u.searchParams.set('f_WT','2');
        else u.searchParams.delete('f_WT');
        link.href=u.toString();
      }else if(u.hostname==='ar.indeed.com'){
        u.searchParams.set('l',locationNames[choice]||'Argentina');
        link.href=u.toString();
      }
    });
  }
  regionTabs?.addEventListener('click',()=>queueMicrotask(updatePortalRegion));
  if(quickLinks)new MutationObserver(updatePortalRegion).observe(quickLinks,{childList:true});
  updatePortalRegion();
  const shortcut=document.createElement('div');shortcut.className='hub-search-shortcut';
  const lead=document.createElement('p');lead.className='note';
  lead.textContent='Usá estos portales para búsquedas nuevas o trasladá el tema al radar de avisos ya recopilados.';
  const toRadar=document.createElement('button');toRadar.type='button';toRadar.className='control primary';
  toRadar.id='hubToRadar';toRadar.textContent='Ver esta búsqueda en el radar';
  shortcut.append(toRadar,lead);quick.append(shortcut);
  toRadar.addEventListener('click',()=>{
    const input=quick.querySelector('#quickQuery');
    const typed=String(input?.value||'').trim().slice(0,120);
    const short=typed.match(/GIS|SIG|geolog|miner|python|datos|soporte|operacion|ventas|gastronom|automatiz/i)?.[0]||typed;
    const query=document.getElementById('q'),where=document.getElementById('location'),
      mode=document.getElementById('mode'),listing=document.getElementById('listingLanguage');
    const area=chosenArea();
    if(query)query.value=short;
    if(where)where.value=({CABA:'CABA','Buenos Aires':'Buenos Aires',Córdoba:'Córdoba'}[area]||'');
    if(mode)mode.value=area==='Remoto'?'REMOTE':'';
    if(listing)listing.value='ES'; // Spanish listing is not proof of Spanish job requirements.
    for(const control of [query,where,mode,listing].filter(Boolean)){
      control.dispatchEvent(new Event('input',{bubbles:true}));
    }
    vacancies.scrollIntoView({behavior:'smooth',block:'start'});
  });
  // The public orientation selects a destination; existing components own their
  // filtering and data. No parallel search engine or private data handling.
  document.addEventListener('opportunity:workspace-go',event=>{
    const detail=event.detail||{};
    if(detail.view==='buscar'){
      choose('buscar');
      // Fresh orientation starts with a clean view, not stale previous filters.
      document.getElementById('clear')?.click();
      const q=document.getElementById('q'),track=document.getElementById('track'),
        mode=document.getElementById('mode'),listing=document.getElementById('listingLanguage'),
        sourceCheck=document.getElementById('sourceCheck');
      // A full category must not be accidentally narrowed by one keyword.
      if(q)q.value=detail.track?'':String(detail.query||'');
      if(track)track.value=String(detail.track||'');
      if(mode)mode.value=detail.mode==='REMOTE'?'REMOTE':'';
      if(listing)listing.value='';
      if(sourceCheck)sourceCheck.value='';
      for(const input of [q,track,mode,listing,sourceCheck].filter(Boolean)){
        input.dispatchEvent(new Event('input',{bubbles:true}));
      }
      const quickQuery=quick.querySelector('#quickQuery');
      if(quickQuery){
        quickQuery.value=String(detail.query||'empleo');
        quickQuery.dispatchEvent(new Event('input',{bubbles:true}));
      }
      vacancies.scrollIntoView({behavior:'auto',block:'start'});
      return;
    }
    if(detail.view==='empresas'){
      companyMode='discovery';
      choose('empresas');
      if(detail.goal==='freelance'){
        document.querySelector('#remote-targets [data-target-tab="services"]')?.click();
        document.getElementById('remote-targets')?.scrollIntoView({behavior:'auto',block:'start'});
      }else discovery.scrollIntoView({behavior:'auto',block:'start'});
    }
  });

  // The main import button already shares the same Excel with the atlas; keep extra
  // multi-file atlas import available for specialized regional directories.
  atlas.querySelector('#atlasUpload').textContent='Sumar directorio adicional';

  // When a new workbook is imported, show the user's actual directory first.
  let hadPrivate=Number(atlas.querySelector('#atlasCount')?.textContent)||0;
  window.addEventListener('opportunity:atlas-change',()=>{
    const count=Number(atlas.querySelector('#atlasCount')?.textContent)||0;
    if(count>0&&!hadPrivate){
      companyMode='private';
      if(current==='empresas')switchCompanies();
    }
    hadPrivate=count;
  });

  top.querySelector('#hubImport').addEventListener('click',()=>{
    // Canonical file path: existing tracker parser triggers atlas parser
    // via opportunity:local-file. This adds no new upload or storage.
    tracker.querySelector('#trackerImport')?.click();
  });
  function routeHash(){
    const raw=location.hash.replace(/^#/,'');
    const anchors={
      'atlas-empresas':'empresas','discovery-targets':'empresas','atlasRows':'empresas',
      'contexto-productivo':'datos','sourceGrid':'datos',
      'quickTitle':'buscar','cards':'buscar','todayJobs':'buscar',
      'trackerTitle':'seguimiento'
    };
    return VIEWS[raw]?raw:anchors[raw]||null;
  }
  const initial=routeHash()||'orientacion';
  choose(initial,{scroll:false,replace:false});
  window.addEventListener('popstate',()=>{
    const requested=routeHash();
    if(requested&&requested!==current)choose(requested,{scroll:false});
  });
  window.addEventListener('hashchange',()=>{
    const requested=routeHash();
    if(requested&&requested!==current)choose(requested,{scroll:false});
  });
  // The discovery links are separate source lookups; direct internal navigation
  // remains available through stable view hash even if the layout is rearranged.
  const sheetNote=document.createElement('p');
  sheetNote.className='hub-context-note';
  sheetNote.textContent='La orientación, las vacantes y el directorio público funcionan sin Excel. El seguimiento personal es opcional y queda en tu navegador. Domicilio, vacante y modalidad no son lo mismo.';
  top.insertAdjacentElement('afterend',sheetNote);
})();
