/* Opportunity OS — single workspace navigation over existing modules.
   No state migrations, no duplicate data ingestion, no backend changes. */
(() => {
  'use strict';
  const nav=document.querySelector('.clarity-nav');
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
  if(!nav||!quick||!routes||!atlas||!discovery||!tracker||!cep||!today||!vacancies) return;
  const VIEWS={
    buscar:{label:'Buscar trabajo',hint:'Vacantes verificables y búsquedas directas, priorizando oportunidades en español.',sections:[quick,routes,statrow,today,vacancies]},
    empresas:{label:'Empresas',hint:'Organizaciones y organismos de tu directorio, más objetivos públicos para investigar.',sections:[atlas,discovery]},
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
  const icons={buscar:'01',empresas:'02',seguimiento:'03',datos:'04'};
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
  const initial=routeHash()||'buscar';
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
  sheetNote.textContent='Fuente de verdad: tu Excel. Las empresas públicas para investigar y los indicadores CEP XXI no cuentan como postulaciones ni se fusionan automáticamente con tus contactos.';
  top.insertAdjacentElement('afterend',sheetNote);
})();
