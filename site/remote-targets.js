/* Remote careers and freelance services: curated public targets, no private data or automated outreach. */
(() => {
  'use strict';
  const discovery=document.getElementById('discovery-targets');
  const quick=document.querySelector('.quick-panel');
  if(!discovery||!quick)return;
  const host=document.createElement('section');
  host.className='remote-targets';
  host.id='remote-targets';
  host.setAttribute('aria-labelledby','remoteTargetsTitle');
  host.innerHTML=[
    '<div class="remote-target-head"><div><span class="micro eyebrow">OBJETIVOS CONCRETOS / NOVIEMBRE 2026</span>',
    '<h3 id="remoteTargetsTitle">Empleo remoto o clientes freelance</h3>',
    '<p class="note">Dos caminos de ingresos. Los empleos deben aceptar postulantes desde Argentina y decir remoto; las empresas a las que ofrecer servicios necesitan un problema comprobable. Nada se envía automáticamente.</p></div>',
    '<span class="remote-only-label">REMOTO · ARGENTINA</span></div>',
    '<div class="remote-target-tabs" role="tablist" aria-label="Tipo de oportunidad">',
    '<button type="button" role="tab" aria-controls="remoteTargetCards" aria-selected="true" class="active" data-target-tab="career">5 empresas / contrato remoto</button>',
    '<button type="button" role="tab" aria-controls="remoteTargetCards" aria-selected="false" data-target-tab="services">Ofrecer servicios freelance</button></div>',
    '<p class="note remote-target-guidance" id="remoteTargetGuidance"></p>',
    '<div id="remoteTargetCards" class="remote-target-cards" role="tabpanel"><p class="note">Cargando objetivos respaldados por fuentes…</p></div>',
    '<p class="note remote-target-foot">Sin cifras verificadas de plantilla argentina ni sueldo comparable en la mayoría de las empresas: no se inventan. La cultura de cada equipo y las remuneraciones reales deben confirmarse en entrevistas. Fecha de revisión: 04/11/2026.</p>'
  ].join('');
  discovery.insertAdjacentElement('afterbegin',host);
  const grid=host.querySelector('#remoteTargetCards');
  const guidance=host.querySelector('#remoteTargetGuidance');
  const buttons=[...host.querySelectorAll('[data-target-tab]')];
  const safeLink=url=>{
    try { const u=new URL(url); return u.protocol==='https:'?u.href:null; }
    catch{return null;}
  };
  const link=(parent,label,href,primary=false)=>{
    const uri=safeLink(href);if(!uri)return;
    const a=document.createElement('a');a.href=uri;a.target='_blank';a.rel='noopener noreferrer';
    a.textContent=label+' ↗';a.className=primary?'remote-primary':'remote-secondary';parent.append(a);
  };
  const put=(parent,tag,content,className)=>{
    const el=document.createElement(tag);el.textContent=content;
    if(className)el.className=className;parent.append(el);return el;
  };
  let tab='career',catalog=null;
  function drawCareer(item){
    const card=put(grid,'article','','remote-target-card');
    const header=put(card,'div','','remote-card-head');
    const num=put(header,'span',String(item.rank).padStart(2,'0'),'remote-rank');
    const info=put(header,'div','','remote-title');
    put(info,'h4',item.name);
    put(info,'p',item.kind==='contract'?'Proyecto freelance / contract':'Empleo remoto por puesto','note');
    put(card,'p',item.pitch,'remote-pitch');
    const fields=[
      ['Modalidad comprobada',item.remote],
      ['Idioma / barrera',item.english],
      ['Remuneración',item.pay],
      ['Dificultad',item.difficulty]
    ];
    const dl=put(card,'dl','','remote-facts');
    fields.forEach(([label,value])=>{
      const group=put(dl,'div','','remote-fact');
      put(group,'dt',label);put(group,'dd',value);
    });
    put(card,'p',item.recommendedAction,'remote-next');
    const actions=put(card,'div','','remote-card-actions');
    link(actions,item.kind==='contract'?'Ver proyecto remoto':'Buscar roles remotos',item.rolesUrl,true);
    if(item.evidenceUrl!==item.rolesUrl)link(actions,'Ver evidencia de modalidad',item.evidenceUrl);
  }
  function drawService(item){
    const card=put(grid,'article','','remote-target-card remote-service-card');
    put(card,'h4',item.label);
    put(card,'p','Clientes posibles: '+item.target,'remote-pitch');
    const d=put(card,'dl','','remote-facts');
    [['Entrega acotada',item.deliverable],['Antes de ofrecerlo',item.evidence]].forEach(([label,value])=>{
      const r=put(d,'div','','remote-fact');put(r,'dt',label);put(r,'dd',value);
    });
    put(card,'p',item.next,'remote-next');
    const actions=put(card,'div','','remote-card-actions');
    link(actions,'Buscar negocios por rubro','https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(item.target.split(',')[0]+' Argentina'));
  }
  function render(){
    buttons.forEach(b=>{
      const selected=b.dataset.targetTab===tab;
      b.classList.toggle('active',selected);b.setAttribute('aria-selected',String(selected));b.tabIndex=selected?0:-1;
    });
    grid.replaceChildren();
    if(!catalog){put(grid,'p','No se pudo cargar la selección. Podés seguir usando los directorios y portales oficiales.','note');return;}
    guidance.textContent=tab==='career'?
      'La empresa puede trabajar en Argentina y aun así publicar vacantes híbridas: aplicá solo cuando el puesto diga Remote / 100% remoto desde Argentina. Ojo con inglés B2/avanzado.' :
      'Ofrecé una mejora concreta después de revisar el sitio y la operación del negocio. «No encontré web propia» no es lo mismo que afirmar «no tiene web». El cliente puede estar en cualquier provincia: la entrega es remota.';
    if(tab==='career')catalog.targets.forEach(drawCareer);
    else catalog.services.forEach(drawService);
  }
  buttons.forEach(b=>b.addEventListener('click',()=>{tab=b.dataset.targetTab;render();}));
  host.querySelector('.remote-target-tabs').addEventListener('keydown',event=>{
    if(!['ArrowLeft','ArrowRight'].includes(event.key))return;
    event.preventDefault();tab=tab==='career'?'services':'career';render();
    host.querySelector('[data-target-tab="'+tab+'"]')?.focus();
  });
  (async()=>{
    try{
      const response=await fetch('/remote-targets-2026.json',{cache:'force-cache'});
      if(!response.ok)throw Error('HTTP '+response.status);
      const data=await response.json();
      if(data.schema_version!==1||data.reviewed_on!=='2026-11-04'||
        !Array.isArray(data.targets)||data.targets.length!==5||
        !Array.isArray(data.services)||data.services.length!==4||
        data.targets.some(x=>!x.name||!safeLink(x.rolesUrl)||!safeLink(x.evidenceUrl)))throw Error('Invalid target snapshot');
      catalog=data;
    }catch{}
    render();
  })();
  // Preserve existing public job feed, but only remote jobs are prioritized in this user's search.
  const mode=document.getElementById('mode');
  if(mode){
    mode.value='REMOTE';
    mode.dispatchEvent(new Event('input',{bubbles:true}));
    const label=mode.closest('label');
    if(label?.querySelector('span'))label.querySelector('span').textContent='Modalidad · priorizar remoto';
  }
  // Keep the remote preference when the user clears the other job filters.
  const clear=document.getElementById('clear');
  if(clear&&mode)clear.addEventListener('click',()=>{
    mode.value='REMOTE';mode.dispatchEvent(new Event('input',{bubbles:true}));
  });
})();
