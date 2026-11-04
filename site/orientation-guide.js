/* Public orientation: no account, Excel, private contact data or API key required. */
(() => {
  'use strict';
  const anchor=document.querySelector('.statrow');
  if(!anchor)return;

  const topics={
    general:{label:'Cualquier área',query:'',track:'',search:'empleo'},
    geo:{label:'GIS · Geociencias · Minería',query:'GIS',track:'gis_geoscience',search:'GIS geoespacial'},
    software:{label:'Python · Software · Datos',query:'Python',track:'software_ai',search:'Python datos'},
    support:{label:'Soporte técnico · Aplicaciones',query:'soporte',track:'',search:'soporte técnico'},
    operations:{label:'Gestión · Operaciones',query:'operaciones',track:'management_operations',search:'operaciones'},
    agro:{label:'Agro · Ambiente',query:'agro',track:'environment_agro',search:'agro ambiente'},
    dining:{label:'Gastronomía · Turismo',query:'gastronomía',track:'income_operations',search:'encargado gastronomía'},
    design:{label:'Diseño · Web',query:'diseño',track:'design_web',search:'diseño web'}
  };
  const goals={
    jobs:{label:'Encontrar empleo',desc:'Buscar vacantes y comprobar requisitos antes de postular.',action:'Explorar vacantes del radar'},
    companies:{label:'Conocer empresas',desc:'Descubrir organizaciones con fuentes públicas, aunque no tengan una vacante publicada.',action:'Explorar directorio público'},
    freelance:{label:'Conseguir clientes',desc:'Identificar negocios a los que ofrecer una entrega concreta, sin inventar necesidades.',action:'Explorar servicios freelance'}
  };
  const modes={
    remote:{label:'100 % remoto',desc:'La modalidad del aviso no prueba que contraten desde tu país.'},
    all:{label:'Todas las modalidades',desc:'La sede de la empresa y la ubicación del puesto son datos distintos.'}
  };
  const params=new URLSearchParams(window.location.search);
  const valid=(value,table,fallback)=>Object.prototype.hasOwnProperty.call(table,value)?value:fallback;
  let goal=valid(params.get('objetivo'),goals,'jobs');
  let topic=valid(params.get('area'),topics,'general');
  let mode=valid(params.get('modalidad'),modes,'remote');

  const section=document.createElement('section');
  section.className='orientation-guide';
  section.id='orientacion';
  section.setAttribute('aria-labelledby','orientationTitle');
  section.innerHTML=[
    '<div class="orientation-intro"><div><div class="micro eyebrow">BRÚJULA / ORIENTACIÓN ABIERTA</div>',
    '<h2 id="orientationTitle">¿Por dónde empezamos?</h2>',
    '<p class="note">Elegí un objetivo y un área. Te mostramos una primera acción posible con los datos públicos que ya tiene Opportunity OS. No necesitás cuenta, CV ni Excel.</p></div>',
    '<span class="orientation-public">PÚBLICO · SIN REGISTRO</span></div>',
    '<div class="orientation-grid">',
    '<div class="orientation-choices">',
    '<fieldset><legend><span class="orientation-step">01</span> ¿Qué necesitás?</legend><div id="orientationGoals" class="orientation-options"></div></fieldset>',
    '<fieldset><legend><span class="orientation-step">02</span> ¿En qué área?</legend><label class="orientation-select-label" for="orientationTopic">Elegí una especialidad o explorá todas</label><select id="orientationTopic"></select></fieldset>',
    '<fieldset><legend><span class="orientation-step">03</span> ¿Qué modalidad?</legend><div id="orientationModes" class="orientation-options orientation-modes"></div></fieldset>',
    '</div>',
    '<div class="orientation-result" aria-live="polite">',
    '<div class="micro eyebrow">TU PRIMERA ACCIÓN</div>',
    '<h3 id="orientationResultTitle"></h3><p id="orientationResultDescription"></p>',
    '<p class="orientation-constraint" id="orientationConstraint"></p>',
    '<button type="button" class="control primary orientation-main-action" id="orientationGo"></button>',
    '<div class="orientation-links"><a id="orientationExternal" href="#" target="_blank" rel="noopener noreferrer"></a>',
    '<button type="button" class="orientation-text-button" id="orientationGemini">Pensarlo con Gemini</button></div>',
    '<p class="orientation-foot">Vacantes, domicilios y condiciones se verifican en sus fuentes originales. Las empresas listadas no necesariamente están contratando.</p>',
    '</div></div>',
    '<div class="orientation-bottom"><span>Tu ruta se puede compartir; no guarda datos personales.</span>',
    '<button id="orientationShare" class="orientation-text-button" type="button">Copiar enlace a esta ruta</button>',
    '<span id="orientationStatus" role="status" aria-live="polite"></span></div>'
  ].join('');
  anchor.insertAdjacentElement('beforebegin',section);
  const $=id=>section.querySelector('#'+id);
  const makeOptions=(container,values,selected,onPick)=>{
    container.replaceChildren();
    Object.entries(values).forEach(([id,item])=>{
      const b=document.createElement('button');
      b.type='button';b.dataset.option=id;b.textContent=item.label;
      b.className='orientation-choice'+(selected===id?' active':'');
      b.setAttribute('aria-pressed',String(selected===id));
      b.addEventListener('click',()=>onPick(id));
      container.append(b);
    });
  };
  for(const [id,item] of Object.entries(topics)){
    const option=document.createElement('option');
    option.value=id;option.textContent=item.label;
    $('orientationTopic').append(option);
  }
  $('orientationTopic').addEventListener('change',event=>{
    topic=valid(event.target.value,topics,'general');render();
  });
  const externalUrl=()=>{
    const terms=topics[topic].search+(mode==='remote'?' remoto':'');
    if(goal==='freelance')return 'https://www.workana.com/es/jobs?query='+encodeURIComponent(topics[topic].search);
    if(goal==='companies')return 'https://cessi.org.ar/directorio-de-empresas/';
    const qs=new URLSearchParams({keywords:terms,location:'Argentina'});
    if(mode==='remote')qs.set('f_WT','2');
    return 'https://www.linkedin.com/jobs/search/?'+qs.toString();
  };
  function shareUrl(){
    const u=new URL(window.location.href);
    u.searchParams.set('objetivo',goal);
    u.searchParams.set('area',topic);
    u.searchParams.set('modalidad',mode);
    u.hash='orientacion';
    return u.toString();
  }
  function render(){
    makeOptions($('orientationGoals'),goals,goal,id=>{goal=id;render();});
    makeOptions($('orientationModes'),modes,mode,id=>{mode=id;render();});
    $('orientationTopic').value=topic;
    const g=goals[goal],t=topics[topic],m=modes[mode];
    $('orientationResultTitle').textContent=g.label+' · '+t.label;
    $('orientationResultDescription').textContent=g.desc;
    $('orientationConstraint').textContent=goal==='jobs'
      ? (mode==='remote'?'Filtro inicial: ofertas remotas. Comprobá también país admitido, idioma y vigencia.':'Búsqueda abierta a varias modalidades; revisá ubicación e idioma antes de postular.')
      : (goal==='companies'?'Directorio público: la ubicación publicada no confirma empleo remoto ni contratación.':
        'Primero verificá una necesidad real del negocio; el directorio no representa pedidos de presupuesto.');
    $('orientationGo').textContent=g.action;
    $('orientationExternal').href=externalUrl();
    $('orientationExternal').textContent=goal==='companies'?'Consultar fuente CESSI':goal==='freelance'?'Buscar proyectos en Workana':'Abrir búsqueda en LinkedIn';
    $('orientationStatus').textContent='';
  }
  $('orientationGo').addEventListener('click',()=>{
    document.dispatchEvent(new CustomEvent('opportunity:workspace-go',{
      detail:{view:goal==='jobs'?'buscar':'empresas',goal,query:topics[topic].query,track:topics[topic].track,mode:mode==='remote'?'REMOTE':''}
    }));
  });
  $('orientationShare').addEventListener('click',async()=>{
    try{
      await navigator.clipboard.writeText(shareUrl());
      $('orientationStatus').textContent='Enlace copiado.';
    }catch{
      $('orientationStatus').textContent='Enlace para copiar: '+shareUrl();
    }
  });
  $('orientationGemini').addEventListener('click',()=>{
    const dialog=document.getElementById('briefDialog');
    const textarea=document.getElementById('briefText');
    if(!dialog||!textarea)return;
    const text=[
      'Ayudame a orientar una búsqueda laboral con pasos concretos, sin inventar ofertas, sueldos ni empresas.',
      'Objetivo: '+goals[goal].label+'.',
      'Área: '+topics[topic].label+'.',
      'Modalidad: '+modes[mode].label+'. Región de búsqueda: Argentina.',
      'Proponé: (1) tres perfiles o tipos de cliente, (2) palabras clave útiles,',
      '(3) cómo verificar modalidad, idioma, elegibilidad y vigencia,',
      '(4) tres acciones pequeñas para hoy. Diferenciá hipótesis de datos comprobados.',
      'Si mencionás una vacante, pedí verificar la publicación oficial.'
    ].join('\n');
    textarea.value=text;
    document.getElementById('copyBriefStatus').textContent='';
    dialog.showModal();
  });
  render();
})();
