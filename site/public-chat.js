/* Embedded public Gemini chat: the browser never receives a Gemini API key. */
(() => {
  'use strict';
  const compass=document.getElementById('orientacion');
  if(!compass)return;
  const root=document.createElement('section');
  root.className='public-chat';
  root.id='chat';
  root.setAttribute('aria-labelledby','publicChatTitle');
  root.innerHTML=[
    '<div class="public-chat-head"><div><span class="micro eyebrow">PREGUNTÁ CON DATOS / GEMINI</span>',
    '<h2 id="publicChatTitle">¿Y si exploramos tus opciones?</h2>',
    '<p class="note">Preguntá por sectores, empresas y vacantes. El chat usa el radar público y fuentes laborales; las respuestas distinguen evidencia de hipótesis.</p></div>',
    '<span class="public-chat-status" id="chatAvailability">Revisando conexión…</span></div>',
    '<div class="public-chat-suggestions" role="group" aria-label="Consultas sugeridas">',
    '<button type="button" data-question="¿Conviene buscar empleo en comercio y servicios o en minería? Explicame qué miden las cifras y qué no.">¿Comercio o minería?</button>',
    '<button type="button" data-question="¿Qué tipos de roles remotos podría investigar desde Argentina si sé Python, GIS y operaciones? No inventes ofertas.">Remoto + GIS + datos</button>',
    '<button type="button" data-question="¿Cómo distinguir empresas con vacantes reales de empresas para contactar con una propuesta freelance?">¿Empleo o freelance?</button></div>',
    '<div class="public-chat-stream" id="chatStream" role="log" aria-live="polite" aria-relevant="additions" aria-label="Conversación">',
    '<div class="public-chat-welcome">Soy una guía de orientación, no un reclutador. Podés preguntarme qué sectores investigar o pedirme que compare ofertas del radar. Las fuentes aparecen junto a la respuesta.</div></div>',
    '<form id="chatForm" class="public-chat-form">',
    '<label class="sr-only" for="chatMessage">Escribí tu pregunta</label>',
    '<textarea id="chatMessage" rows="2" maxlength="700" placeholder="Ej.: Tengo experiencia en gestión y aprendo Python. ¿Qué tipos de empresas debería investigar primero?" required></textarea>',
    '<button type="submit" class="control primary" id="chatSend">Preguntar</button></form>',
    '<div class="public-chat-footer"><span id="chatFeedback" role="status" aria-live="polite"></span>',
    '<button type="button" id="chatClear" class="public-chat-link">Borrar conversación</button></div>',
    '<p class="public-chat-caveat">Solo datos públicos: no adjuntes CV, teléfonos, correos ni información privada. La conversación no se guarda en Opportunity OS; el texto enviado es procesado por Gemini según las condiciones de su servicio. Las vacantes deben verificarse en la fuente.</p>'
  ].join('');
  compass.insertAdjacentElement('afterend',root);
  const $=id=>root.querySelector('#'+id);
  const stream=$('chatStream'),input=$('chatMessage'),form=$('chatForm');
  let busy=false,history=[],revision=0,activeRequest=null;
  const add=(role,text,sources=[])=>{
    const article=document.createElement('article');
    article.className='public-chat-turn '+(role==='user'?'user':'assistant');
    const tag=document.createElement('span');tag.className='public-chat-role';
    tag.textContent=role==='user'?'PREGUNTA':role==='system'?'ESTADO DEL SERVICIO':'GEMINI · FUENTES PÚBLICAS';
    const body=document.createElement('div');body.className='public-chat-text';
    body.textContent=text;article.append(tag,body);
    if(sources.length){
      const refs=document.createElement('div');refs.className='public-chat-references';
      const label=document.createElement('span');label.textContent='Fuentes disponibles';refs.append(label);
      const seen=new Set();
      sources.filter(s=>s&&typeof s.url==='string').forEach(s=>{
        let u;try{u=new URL(s.url);}catch{return;}
        if(u.protocol!=='https:'||seen.has(u.href))return;
        seen.add(u.href);
        const a=document.createElement('a');
        a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';
        a.textContent=String(s.id||'')+' · '+String(s.label||'Ver fuente').slice(0,65);
        refs.append(a);
      });
      if(seen.size)article.append(refs);
    }
    stream.append(article);
    stream.scrollTop=stream.scrollHeight;
  };
  const params=()=>({
    goal:document.getElementById('orientationGoals')?.querySelector('[aria-pressed="true"]')?.textContent?.trim()||'',
    area:document.getElementById('orientationTopic')?.selectedOptions?.[0]?.textContent||'',
    mode:document.getElementById('orientationModes')?.querySelector('[aria-pressed="true"]')?.textContent?.trim()||'',
    scope:document.getElementById('orientationScope')?.querySelector('[aria-pressed="true"]')?.textContent?.trim()||''
  });
  function setBusy(value){
    busy=value;
    $('chatSend').disabled=value;input.disabled=value;
    $('chatSend').textContent=value?'Consultando…':'Preguntar';
  }
  async function send(value){
    const message=String(value||'').trim().slice(0,700);
    if(busy||message.length<3)return;
    const requestId=++revision;
    const controller=new AbortController();
    activeRequest=controller;
    const chosen=params();
    const prepared=message+'\nContexto elegido en la brújula (preferencias del visitante, no evidencia): '+[chosen.goal,chosen.area,chosen.mode,chosen.scope].filter(Boolean).join(' · ');
    add('user',message);
    input.value='';$('chatFeedback').textContent='Consultando datos públicos y Gemini…';setBusy(true);
    const currentHistory=history.slice(-4);
    try{
      const r=await fetch('/api/chat',{
        method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message:prepared.slice(0,700),history:currentHistory}),
        signal:controller.signal
      });
      const data=await r.json().catch(()=>({}));
      if(requestId!==revision)return;
      if(!r.ok)throw Error(typeof data.error==='string'?data.error:'Error HTTP '+r.status);
      if(typeof data.answer!=='string'||!data.answer.trim())throw Error('La respuesta llegó vacía.');
      add('model',data.answer,Array.isArray(data.sources)?data.sources:[]);
      history.push({role:'user',text:prepared.slice(0,550)},{role:'model',text:data.answer.slice(0,550)});
      history=history.slice(-4);
      const stamp=data.generated_at&&data.generated_at!=='No disponible'?
        'Captura del radar: '+String(data.generated_at).slice(0,22):'Sin fecha verificable del radar.';
      const counts=data.radar_summary;
      const measured=Number.isInteger(counts?.coincidencias_filtro)&&Number.isInteger(counts?.avisos_en_captura)?
        'Filtro calculado: '+counts.coincidencias_filtro+' de '+counts.avisos_en_captura+' avisos de la captura. ':'';
      $('chatFeedback').textContent=measured+(data.feed_available?'Radar público consultado. ':'Radar no disponible. ')+stamp;
    }catch(error){
      if(requestId!==revision)return;
      add('system',String(error.message||'No se pudo completar la consulta.').slice(0,270));
      $('chatFeedback').textContent='La consulta no se completó. No mostramos respuestas inventadas.';
    }finally{
      if(requestId===revision){activeRequest=null;setBusy(false);input.focus();}
    }
  }
  form.addEventListener('submit',event=>{event.preventDefault();send(input.value);});
  root.querySelectorAll('[data-question]').forEach(b=>b.addEventListener('click',()=>send(b.dataset.question)));
  $('chatClear').addEventListener('click',()=>{
    revision++;
    activeRequest?.abort();activeRequest=null;setBusy(false);
    history=[];stream.replaceChildren();
    add('system','Conversación borrada de esta página. Los mensajes anteriores no se enviarán en nuevas consultas.');
    $('chatFeedback').textContent='';
  });
  (async()=>{
    try{
      const response=await fetch('/api/chat',{headers:{accept:'application/json'},cache:'no-store'});
      const data=await response.json();
      $('chatAvailability').textContent=data.enabled?'Gemini conectado':'Gemini no disponible en esta versión';
      $('chatAvailability').dataset.connected=String(Boolean(data.enabled));
    }catch{
      $('chatAvailability').textContent='Conexión no comprobada';
    }
  })();
})();
