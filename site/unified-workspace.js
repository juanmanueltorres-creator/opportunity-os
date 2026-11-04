/* Opportunity OS — unified task flow. Reuses live modules; never clones private records. */
(() => {
  'use strict';
  const quick=document.querySelector('.quick-panel');
  const atlas=document.getElementById('atlas-empresas');
  const discovery=document.getElementById('discovery-targets');
  const cep=document.getElementById('contexto-productivo');
  const tracker=document.querySelector('.tracker-panel');
  const nav=document.querySelector('.clarity-nav');
  const routes=document.querySelector('.clarity-routes');
  if(!quick||!atlas||!discovery||!cep||!tracker||!routes||!nav)return;

  // One search panel: specialty + location + job portals.
  const tabs=routes.querySelector('#routeTabs');
  const regionDesc=routes.querySelector('#routeDescription');
  const regionLinks=routes.querySelector('#routeLinks');
  const specialties=quick.querySelector('#quickChips');
  const quickLinks=quick.querySelector('#quickPortalLinks');
  const quickInput=quick.querySelector('#quickQuery');
  if(!tabs||!regionDesc||!regionLinks||!specialties||!quickLinks||!quickInput)return;
  const scope=document.createElement('div');
  scope.className='unified-scope';
  const title=document.createElement('h3');title.textContent='Zona de búsqueda';
  const expl=document.createElement('p');expl.className='note';expl.textContent='Empezá por todo el país. Provincia y remoto son opciones, no límites automáticos.';
  const extra=document.createElement('details');extra.className='unified-region-extras';
  const summary=document.createElement('summary');summary.textContent='Otros portales y fuentes para esta zona';
  extra.append(summary,regionLinks);
  scope.append(title,tabs,regionDesc,expl,extra);
  specialties.insertAdjacentElement('afterend',scope);
  routes.remove();

  // Keep one place to start a job search; the original quick links now follow the selected region.
  const areas={
    'Todo el país':{location:'Argentina',province:'',discovery:'Todas'},
    'Buenos Aires':{location:'Provincia de Buenos Aires, Argentina',province:'Buenos Aires',discovery:'PBA'},
    'CABA':{location:'Ciudad Autónoma de Buenos Aires, Argentina',province:'CABA',discovery:'CABA'},
    'Córdoba':{location:'Córdoba, Argentina',province:'Córdoba',discovery:'Otras provincias'},
    'Remoto':{location:'Argentina',province:'',remote:true,discovery:'Todas'}
  };
  let activeRegion='Todo el país';
  const getArea=()=>areas[activeRegion]||areas['Todo el país'];
  const followArea=()=>{
    quickLinks.querySelectorAll('a[href]').forEach(link=>{
      let url;try{url=new URL(link.href)}catch{return}
      if(url.hostname==='www.linkedin.com'&&url.pathname.startsWith('/jobs/search')){
        url.searchParams.set('location',getArea().location);
        if(getArea().remote)url.searchParams.set('f_WT','2');
        else url.searchParams.delete('f_WT');
        link.href=url.toString();
      }else if(url.hostname==='ar.indeed.com'){
        url.searchParams.set('l',getArea().location);
        link.href=url.toString();
      }
    });
  };
  new MutationObserver(followArea).observe(quickLinks,{childList:true});
  tabs.addEventListener('click',event=>{
    const button=event.target.closest('button.clarity-destination');
    if(!button)return;
    activeRegion=button.textContent.trim();
    queueMicrotask(()=>{followArea();updateActionLabels();});
  });
  followArea();
  const actions=document.createElement('div');
  actions.className='unified-start-actions';
  actions.innerHTML='<button type="button" class="control" id="unifiedCompanies">Ver empresas de esta zona</button>'+
    '<button type="button" class="control" id="unifiedRadar">Explorar esta búsqueda en el radar</button>'+
    '<p class="note" id="unifiedActionNote">Los resultados externos requieren comprobar vigencia, idioma y elegibilidad desde Argentina.</p>';
  quick.append(actions);

  // One company workspace: private directory, vetted public leads, historical territorial indicators.
  const sourcePanel=atlas.querySelector('.atlas-sources');
  const ownNodes=['.atlas-stats','.atlas-controls','.atlas-geo','.atlas-workspace']
    .map(s=>atlas.querySelector(s));
  if(!sourcePanel||ownNodes.some(n=>!n))return;
  const wrapper=document.createElement('div');wrapper.className='unified-directory';
  const tablist=document.createElement('div');tablist.className='unified-directory-tabs';
  tablist.setAttribute('role','tablist');tablist.setAttribute('aria-label','Vistas de empresas y territorio');
  const panels={};
  const definitions=[
    ['private','Mi directorio','Empresas y organismos de mi Excel'],
    ['discovery','Descubrir empresas','Fichas públicas con fuente'],
    ['context','Estadísticas provinciales','CEP XXI · 2022']
  ];
  const status=document.createElement('p');status.className='unified-view-hint note';
  const views=document.createElement('div');views.className='unified-directory-views';
  definitions.forEach(([key,label,desc])=>{
    const button=document.createElement('button');button.type='button';button.dataset.workspace=key;
    button.className='unified-dir-tab';
    button.setAttribute('role','tab');
    button.setAttribute('aria-controls','unified-view-'+key);
    button.textContent=label;
    tablist.append(button);
    const panel=document.createElement('div');panel.className='unified-dir-view';
    panel.id='unified-view-'+key;panel.setAttribute('role','tabpanel');panel.hidden=true;
    panel.setAttribute('aria-label',desc);views.append(panel);panels[key]=panel;
  });
  ownNodes.forEach(node=>panels.private.append(node));
  panels.discovery.append(discovery);
  panels.context.append(cep);
  wrapper.append(tablist,status,views);
  atlas.insertBefore(wrapper,sourcePanel);

  const privateCount=()=>Number(atlas.querySelector('#atlasCount')?.textContent)||0;
  let current=privateCount()>0?'private':'discovery';
  const activate=(name,scroll=false)=>{
    current=panels[name]?name:'private';
    for(const [key,panel] of Object.entries(panels)){
      const show=key===current;panel.hidden=!show;
      const tab=tablist.querySelector('[data-workspace="'+key+'"]');
      tab.classList.toggle('active',show);
      tab.setAttribute('aria-selected',String(show));
      tab.tabIndex=show?0:-1;
    }
    const hints={
      private:privateCount()>0?'Mostrando '+privateCount()+' organizaciones importadas. Tu Excel sigue siendo la fuente de verdad.':'Sin directorio cargado. Usá «Sumar Excel / directorio»; no necesitás escribir cada empresa otra vez.',
      discovery:'Fichas públicas para investigar. No se suman a tus contactos ni representan vacantes abiertas.',
      context:'Datos de empleo y establecimientos de 2022. No son cifras de contratación actual ni de empresas individuales.'
    };
    status.textContent=hints[current];
    if(scroll)atlas.scrollIntoView({behavior:'smooth',block:'start'});
  };
  tablist.addEventListener('click',event=>{
    const button=event.target.closest('button[data-workspace]');
    if(button)activate(button.dataset.workspace);
  });
  tablist.addEventListener('keydown',event=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    const all=[...tablist.querySelectorAll('button[data-workspace]')];
    const index=all.findIndex(b=>b.dataset.workspace===current);
    let next=index;
    if(event.key==='ArrowLeft')next=(index+all.length-1)%all.length;
    else if(event.key==='ArrowRight')next=(index+1)%all.length;
    else if(event.key==='Home')next=0;
    else if(event.key==='End')next=all.length-1;
    event.preventDefault();activate(all[next].dataset.workspace);all[next].focus();
  });
  activate(current);

  // Navigation is about tasks, not an exhaustive index of every widget.
  nav.replaceChildren();
  const badge=document.createElement('span');badge.className='micro';badge.textContent='FLUJO';nav.append(badge);
  const navTargets=[
    ['01 · Buscar', '#quickTitle',null],
    ['02 · Empresas','#atlas-empresas',current==='private'?'private':'discovery'],
    ['03 · Vacantes','#cards',null],
    ['04 · Seguimiento','#trackerTitle',null],
    ['Datos 2022','#contexto-productivo','context']
  ];
  navTargets.forEach(([label,href,view])=>{
    const link=document.createElement('a');link.href=href;link.textContent=label;
    if(view)link.addEventListener('click',event=>{
      event.preventDefault();
      activate(view==='context'?'context':privateCount()>0?'private':'discovery');
      atlas.scrollIntoView({behavior:'smooth',block:'start'});
    });
    nav.append(link);
  });

  function updateActionLabels(){
    const button=actions.querySelector('#unifiedCompanies');
    button.textContent=getArea().remote?'Explorar empresas (remoto por verificar)':
      getArea().province?'Ver empresas · '+activeRegion:'Explorar empresas';
    actions.querySelector('#unifiedActionNote').textContent=getArea().remote?
      'Remoto describe un aviso, no la sede de una empresa. Verificá países admitidos en cada oferta.':
      'Los enlaces externos no implican vacantes abiertas. Las empresas públicas conservan su fuente.';
  }
  updateActionLabels();
  actions.querySelector('#unifiedCompanies').addEventListener('click',()=>{
    const area=getArea(), privateSelect=atlas.querySelector('#atlasProvince');
    if(area.province==='Córdoba'&&privateCount()>0&&privateSelect){
      activate('private',true);
      privateSelect.value='Córdoba';privateSelect.dispatchEvent(new Event('input',{bubbles:true}));
      return;
    }
    activate('discovery',true);
    const region=area.discovery;
    const choices=[...discovery.querySelectorAll('#discoveryRegions button')];
    const choice=choices.find(b=>region==='PBA'?b.textContent.startsWith('PBA'):
      region==='CABA'?b.textContent.startsWith('CABA'):
      region==='Otras provincias'?b.textContent.startsWith('Otras'):b.textContent.startsWith('Todas'));
    choice?.click();
  });
  actions.querySelector('#unifiedRadar').addEventListener('click',()=>{
    const area=getArea();
    const search=document.getElementById('q');
    const loc=document.getElementById('location');
    const mode=document.getElementById('mode');
    const listing=document.getElementById('listingLanguage');
    if(search){
      const value=quickInput.value.trim().slice(0,120);
      // The public feed matches text; longer compound queries tend to hide valid openings.
      const simple=value.match(/GIS|SIG|geolog|miner|python|datos|soporte|operacion|venta|gastronom|automatiz/i)?.[0]||value;
      search.value=simple;
    }
    if(loc)loc.value=area.remote?'':area.province;
    if(mode)mode.value=area.remote?'REMOTE':'';
    if(listing)listing.value='ES'; // Spanish listing only; not a verified Spanish-speaking workplace.
    [search,loc,mode,listing].filter(Boolean).forEach(el=>el.dispatchEvent(new Event('input',{bubbles:true})));
    document.getElementById('cards')?.scrollIntoView({behavior:'smooth',block:'start'});
  });

  // One Excel can populate both views regardless of which import button the user presses.
  // Keep both buttons for familiarity; their existing handlers remain intact.
  tracker.querySelector('#trackerImport').textContent='Actualizar desde Excel / CSV';
  atlas.querySelector('#atlasUpload').textContent='Sumar empresas desde Excel';
  const trackerHint=tracker.querySelector('.tracker-head .note');
  if(trackerHint)trackerHint.textContent='Un mismo archivo puede alimentar este resumen y el directorio. Los cambios siguen en el Excel original; no se sube nada al servidor.';

  // Reorder by user action: look for opportunities first, then track.
  document.querySelector('main .layout')?.insertAdjacentElement('afterend',tracker);

  const collapseSection=(element,summaryLabel)=>{
    if(!element||element.closest('.unified-secondary'))return;
    const container=document.createElement('details');container.className='unified-secondary';
    const summary=document.createElement('summary');summary.textContent=summaryLabel;
    element.parentNode.insertBefore(container,element);
    container.append(summary,element);
  };
  collapseSection(document.querySelector('main > .territory'),'Ver distribución territorial de los avisos');
  collapseSection(document.querySelector('main > .sources'),'Ver fuentes y portales complementarios');

  let hadEntries=privateCount()>0;
  window.addEventListener('opportunity:atlas-change',()=>{
    const newCount=privateCount();
    if(newCount>0&&!hadEntries){hadEntries=true;activate('private');}
    else if(newCount===0&&hadEntries){hadEntries=false;activate('discovery');}
    else if(current==='private')activate('private');
  });
})();
