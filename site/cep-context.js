/* CEP XXI: contexto productivo oficial separado del atlas privado.
   Los valores del snapshot son puestos/establecimientos históricos, NO vacantes ni empresas individuales. */
(() => {
  'use strict';
  const atlas=document.querySelector('#atlas-empresas');
  const geo=atlas?.querySelector('.atlas-geo');
  if(!geo) return;
  const LABELS={
    A:'Agricultura, ganadería, silvicultura y pesca',
    B:'Explotación de minas y canteras',
    C:'Industria manufacturera',
    D:'Electricidad, gas y vapor',
    E:'Agua, saneamiento y residuos',
    F:'Construcción',
    G:'Comercio y reparación de vehículos',
    H:'Transporte y almacenamiento',
    I:'Alojamiento y servicios de comida',
    J:'Información y comunicaciones',
    K:'Servicios financieros y seguros',
    L:'Actividades inmobiliarias',
    M:'Servicios profesionales, científicos y técnicos',
    N:'Servicios administrativos y de apoyo',
    O:'Administración pública y defensa',
    P:'Enseñanza',
    Q:'Salud y servicios sociales',
    R:'Arte, entretenimiento y recreación',
    S:'Otros servicios',
    T:'Hogares como empleadores',
    U:'Organismos extraterritoriales'
  };
  const SOURCE='https://datos.gob.ar/dataset/produccion-distribucion-geografica-establecimientos-productivos';
  const panel=document.createElement('section');
  panel.className='cep-context';
  panel.id='contexto-productivo';
  panel.setAttribute('aria-labelledby','cepHeading');
  panel.innerHTML=[
    '<div class="cep-head"><div><span class="micro eyebrow">DATOS OFICIALES / CEP XXI / 2022</span>',
    '<h3 id="cepHeading">Contexto productivo por provincia y sector</h3>',
    '<p class="note">Compará dónde se concentran los puestos registrados y los establecimientos productivos. ',
    'Son datos de 2022, no empleos disponibles hoy ni una medida de la reputación de las empresas.</p></div>',
    '<a href="'+SOURCE+'" target="_blank" rel="noopener noreferrer">Ver dataset y metodología ↗</a></div>',
    '<div class="cep-controls"><label>Actividad económica · CLAE letra',
    '<select id="cepActivity"><option value="">Todas las actividades</option></select></label>',
    '<label>Comparar por<select id="cepMetric"><option value="jobs">Puestos registrados</option>',
    '<option value="establishments">Establecimientos</option></select></label>',
    '<button id="cepAll" type="button" class="control">Ver todas las provincias</button></div>',
    '<p id="cepStatus" class="note" role="status" aria-live="polite">Cargando snapshot público 2022…</p>',
    '<div class="cep-kpis" id="cepKpis" hidden><div><span>JURISDICCIÓN</span><strong id="cepPlace">—</strong></div>',
    '<div><span>PUESTOS REGISTRADOS</span><strong id="cepJobs">—</strong></div>',
    '<div><span>ESTABLECIMIENTOS CONTABILIZADOS</span><strong id="cepEst">—</strong></div>',
    '<div><span>AÑO</span><strong id="cepYear">2022</strong></div></div>',
    '<div class="cep-grid" id="cepGrid" hidden><div class="cep-graph">',
    '<h4 id="cepProvinceTitle">Comparación entre jurisdicciones</h4>',
    '<p class="note">Elegí una provincia para filtrar simultáneamente el directorio privado.</p>',
    '<div id="cepProvinceBars" class="cep-bars"></div></div>',
    '<div class="cep-graph"><h4 id="cepSectorTitle">Composición por actividad</h4>',
    '<p class="note">Puestos y establecimientos por sector CLAE. No son empresas únicas ni vacantes.</p>',
    '<div id="cepSectorBars" class="cep-bars cep-sector-bars"></div></div></div>',
    '<p class="note cep-foot">Fuente: CEP XXI, datos SIPA/AFIP. ',
    'Agregación de 2022 por departamento y actividad (CLAE letra). ',
    'Última actualización informada del conjunto: 06/12/2023. ',
    'Snapshot calculado el 04/11/2026. ',
    'Las cifras de empleo representan puestos, no personas; un establecimiento no equivale necesariamente a una empresa. ',
    'Estos valores NO son datos de contratación actual ni se asignan a las organizaciones de tu Excel.</p>'
  ].join('');
  geo.insertAdjacentElement('afterend',panel);
  const $=id=>panel.querySelector('#'+id);
  const pretty=new Intl.NumberFormat('es-AR',{maximumFractionDigits:0});
  const METRICS={jobs:'puestos registrados',establishments:'establecimientos'};
  let data=null, showingAll=false;
  const privateProvince=document.getElementById('atlasProvince');
  const privateCountry=document.getElementById('atlasCountry');
  const privateTerritory=document.getElementById('atlasTerritory');
  function addText(el,value){el.textContent=String(value);}
  function num(row,metric){const v=Number(row?.[metric]);return Number.isFinite(v)&&v>=0?v:0;}
  function total(rows,metric){return rows.reduce((sum,row)=>sum+num(row,metric),0);}
  function selectedProvince(){
    const p=privateProvince?.value||'';
    const c=privateCountry?.value||'';
    if(c && c!=='Argentina')return {foreign:true,province:''};
    return {foreign:false,province:p};
  }
  function configureActivity(){
    const select=$('cepActivity');select.replaceChildren();
    const item=document.createElement('option');item.value='';item.textContent='Todas las actividades';select.append(item);
    Object.entries(LABELS).forEach(([code,label])=>{
      const op=document.createElement('option');op.value=code;op.textContent=code+' · '+label;select.append(op);
    });
  }
  function rowButton(name,value,maximum,active,onclick){
    const root=document.createElement('button');root.type='button';root.className='cep-bar'+(active?' active':'');
    root.setAttribute('aria-pressed',String(Boolean(active)));
    const upper=document.createElement('span');upper.className='cep-bar-label';
    const text=document.createElement('span');text.textContent=name;
    const amount=document.createElement('strong');amount.textContent=pretty.format(value);
    upper.append(text,amount);
    const rail=document.createElement('span');rail.className='cep-bar-rail';
    const fill=document.createElement('span');fill.className='cep-bar-fill';
    fill.style.width=(maximum>0?Math.max(0,Math.min(100,value/maximum*100)):0).toFixed(2)+'%';
    rail.append(fill);root.append(upper,rail);
    root.addEventListener('click',onclick);return root;
  }
  function publicRowsFor(code){
    return code?data.rows.filter(r=>r.code===code):data.rows;
  }
  function setAtlasProvince(province){
    if(!privateProvince||!privateCountry)return;
    if(privateCountry.value!=='Argentina'){
      privateCountry.value='Argentina';
      privateCountry.dispatchEvent(new Event('input',{bubbles:true}));
    }
    privateProvince.value=privateProvince.value===province?'':province;
    privateProvince.dispatchEvent(new Event('input',{bubbles:true}));
    render();
    atlas.querySelector('.atlas-workspace')?.scrollIntoView({behavior:'smooth',block:'nearest'});
  }
  function render(){
    if(!data)return;
    const {foreign,province}=selectedProvince(),code=$('cepActivity').value,
      metric=$('cepMetric').value in METRICS?$('cepMetric').value:'jobs';
    $('cepKpis').hidden=foreign;
    $('cepGrid').hidden=foreign;
    if(foreign){
      addText($('cepStatus'),'Las estadísticas son exclusivamente de Argentina. Elegí Argentina o Todos los países en el atlas.');
      return;
    }
    const selected=publicRowsFor(code);
    const scoped=province?selected.filter(x=>x.province===province):selected;
    $('cepStatus').textContent= (province?province:'Argentina completa')+
      ' · '+(code?code+' · '+LABELS[code]:'todas las actividades')+
      ' · Fuente 2022, no resultados de búsqueda de empleo.';
    $('cepPlace').textContent=province||'Argentina';
    $('cepJobs').textContent=pretty.format(total(scoped,'jobs'));
    $('cepEst').textContent=pretty.format(total(scoped,'establishments'));
    $('cepYear').textContent=String(data.reference_year);
    const provinces=[...new Set(data.rows.map(r=>r.province))];
    const points=provinces.map(name=>({
      name,value:total(selected.filter(r=>r.province===name),metric)
    })).sort((a,b)=>b.value-a.value||a.name.localeCompare(b.name,'es'));
    const maxP=Math.max(0,...points.map(p=>p.value));
    const container=$('cepProvinceBars');container.replaceChildren();
    points.forEach(p=>container.append(rowButton(p.name,p.value,maxP,p.name===province,()=>setAtlasProvince(p.name))));
    $('cepProvinceTitle').textContent='Jurisdicciones · '+METRICS[metric]+' · '+(code?code:'todas las actividades');
    const breakdown=(province?data.rows.filter(r=>r.province===province):data.rows);
    const sectors=Object.keys(LABELS).map(letter=>({
      name:letter+' · '+LABELS[letter],
      code:letter,
      value:total(breakdown.filter(r=>r.code===letter),metric)
    })).sort((a,b)=>b.value-a.value||a.code.localeCompare(b.code));
    const maximum=Math.max(0,...sectors.map(x=>x.value));
    const bars=$('cepSectorBars');bars.replaceChildren();
    const visible=showingAll?sectors:sectors.slice(0,7);
    visible.forEach(x=>bars.append(rowButton(x.name,x.value,maximum,x.code===code,()=>{
      $('cepActivity').value=$('cepActivity').value===x.code?'':x.code;render();
    })));
    if(sectors.length>visible.length||showingAll){
      const more=document.createElement('button');more.type='button';more.className='cep-more';
      more.textContent=showingAll?'Ver solo sectores principales':'Mostrar las 21 actividades';
      more.addEventListener('click',()=>{showingAll=!showingAll;render();});bars.append(more);
    }
    $('cepSectorTitle').textContent='Actividades · '+METRICS[metric]+' · '+(province||'Argentina');
  }
  async function load(){
    try{
      const r=await fetch('/cep-provincial-2022.json',{cache:'force-cache'});
      if(!r.ok)throw Error('HTTP '+r.status);
      const parsed=await r.json();
      if(parsed.schema_version!==1||parsed.reference_year!==2022||!Array.isArray(parsed.rows)||
        parsed.provinces!==24||parsed.rows.length<400||parsed.rows.length>600)throw Error('Formato de fuente inesperado');
      const seen=new Set();
      for(const x of parsed.rows){
        if(typeof x.province!=='string'||!Object.prototype.hasOwnProperty.call(LABELS,x.code)
          ||!Number.isSafeInteger(x.jobs)||!Number.isSafeInteger(x.establishments)
          ||x.jobs<0||x.establishments<0)throw Error('Fila no válida');
        const key=x.province+'|'+x.code;if(seen.has(key))throw Error('Doble sector/provincia: '+key);seen.add(key);
      }
      data=parsed;configureActivity();$('cepKpis').hidden=false;$('cepGrid').hidden=false;render();
    }catch(e){
      $('cepStatus').textContent='El snapshot oficial no está disponible ('+(e.message||'error')+'). Podés consultar el dataset original; no se muestran cifras sin fuente.';
    }
  }
  $('cepActivity').addEventListener('input',()=>{showingAll=false;render();});
  $('cepMetric').addEventListener('input',render);
  $('cepAll').addEventListener('click',()=>{
    if(privateCountry){privateCountry.value='Argentina';privateCountry.dispatchEvent(new Event('input',{bubbles:true}));}
    if(privateProvince){privateProvince.value='';privateProvince.dispatchEvent(new Event('input',{bubbles:true}));}
    render();
  });
  [privateProvince,privateCountry].filter(Boolean).forEach(el=>el.addEventListener('input',()=>queueMicrotask(render)));
  // Clicks sobre las celdas provinciales originales actualizan el valor sin disparar input.
  if(privateTerritory)new MutationObserver(()=>render()).observe(privateTerritory,{childList:true});
  load();
})();
