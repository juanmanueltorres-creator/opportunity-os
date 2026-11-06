/* Deterministic query layer for the public daily radar snapshot.
   It never infers an open vacancy, newly discovered vacancy, or hiring eligibility. */
const plain = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const validTime = value => {
  if(typeof value!=='string' || !/^\d{4}-\d{2}-\d{2}T/.test(value))return null;
  const n=Date.parse(value);return Number.isFinite(n)?n:null;
};
const https = value => {
  try {const u=new URL(value);return u.protocol==='https:'?u.href:null;}
  catch{return null;}
};
const domainRules=[
  {name:'GIS/geoespacial',ask:/\b(gis|sig|qgis|arcgis|geoespacial|geospatial|teledeteccion|cartografia)\b/,match:/\b(gis|sig|qgis|arcgis|geoespacial|geospatial|geospatial|teledeteccion|cartograf\w*|geomatic\w*|remote sensing)\b/},
  {name:'Python',ask:/\b(python|fastapi|django)\b/,match:/\b(python|fastapi|django)\b/},
  {name:'backend',ask:/\b(backend|back.end)\b/,match:/\b(backend|back.end|server.side)\b/},
  {name:'JavaScript/TypeScript',ask:/\b(javascript|typescript|node\.?js|react)\b/,match:/\b(javascript|typescript|node\.?js|react)\b/},
  {name:'Java',ask:/\b(java)\b/,match:/\b(java|spring boot|springboot)\b/},
  {name:'soporte técnico',ask:/\b(soporte|helpdesk|support)\b/,match:/\b(soporte|support|helpdesk|service desk)\b/},
  {name:'minería/geología',ask:/\b(mineria|minero|geologia|geologo|hidrogeologia)\b/,match:/\b(mineria|minero|mining|geolog\w*|hidrogeolog\w*|hydrogeolog\w*)\b/},
  {name:'datos',ask:/\b(datos|data|analista de datos|data engineer)\b/,match:/\b(datos|data|analytics|analitica|analista de datos|analyst)\b/},
  {name:'operaciones',ask:/\b(operaciones|logistica|gestion)\b/,match:/\b(operaciones|operations|logistica|gestion|inventory|supply chain)\b/},
  {name:'gastronomía',ask:/\b(gastronomia|restaurante|cocina)\b/,match:/\b(gastronomia|restaurante|restaurant|cocina|chef|hospitality)\b/},
  {name:'agro/ambiente',ask:/\b(agro|agtech|ambiental|ambiente)\b/,match:/\b(agro|agtech|ambiental|ambiente|environmental|agriculture)\b/}
];
export function planPublicRadarQuery(input){
  // The compass appends optional browsing preferences; only the explicit
  // question is authorized to turn into hard inclusion/exclusion filters.
  const question=plain(String(input??'').split(/\nContexto elegido en la brújula/i)[0]).slice(0,700);
  const comparisonIntent=/\b(desaparec\w*|dejaron de (?:figurar|aparecer)|ya no (?:figuran|aparecen))\b/.test(question)?'no_longer_observed':
    /\b(siguen apareciendo|siguen figurando|presentes en ambas)\b/.test(question)?'continuing':
    /\b(nuevas?|nuevos?|aparecieron|aparecio|incorporad\w*|recien detectad\w*)\b/.test(question)?'newly_observed':
    /\b(cambio|cambiaron|cambios|compar\w*|diferencia\w*|entre capturas|respecto de ayer)\b/.test(question)?'summary':null;
  const windowHours=comparisonIntent?null:/\b(ayer|hoy|ultimas? 24 horas?|ultimas? 24 h|desde ayer)\b/.test(question)?24:
    /\b(esta semana|ultima semana|ultimos? 7 dias|7 dias)\b/.test(question)?168:null;
  const confirmedArgentina=/\b(aceptan?|contratan?|elegib\w*|confirmad\w*)\b.{0,45}\bargentina\b|\bargentina\b.{0,45}\b(aceptan?|contratan?|elegib\w*|confirmad\w*)\b/.test(question);
  const requestedDomains=domainRules.filter(d=>d.ask.test(question));
  // Unknown explicit technologies must not silently become an all-market count.
  const technologies=question.match(/\b(?:de|con|para|en)\s+(?:empleo\s+de\s+|vacantes?\s+de\s+)?(kotlin|rust|golang|go|cobol|php|ruby|flutter|swift|scala|angular|dotnet|\.net|c\+\+|c#)\b/);
  const explicitRole=question.match(/\b(?:vacantes?|empleos?|puestos?|trabajos?)\s+(?:de|para|con)\s+([a-z0-9+#.]+)/);
  const ignored=new Set(['trabajo','empleo','empresa','empresas','argentina','remoto','remotos','remota','remotas','esta','este','hoy','ayer','los','las']);
  const unsupportedTopic=requestedDomains.length===0?(technologies?.[1]||(!ignored.has(explicitRole?.[1])?explicitRole?.[1]:null)):null;
  return {
    publication_window_hours:windowHours,
    comparison_intent:comparisonIntent,
    remote_only:/\b(remoto|remota|remotos|remotas|remote)\b/.test(question),
    confirmed_argentina_only:confirmedArgentina,
    spanish_requirement:/\b(trabajo en espanol|idioma laboral en espanol|idioma de trabajo en espanol|sin ingles|solo espanol)\b/.test(question),
    listing_spanish_only:/\b(avisos? en espanol|publicaciones? en espanol)\b/.test(question),
    topics:requestedDomains.map(d=>d.name),
    unsupported_topic:unsupportedTopic,
    kind:/\b(cuantas|cuantos|cantidad|numero|total)\b/.test(question)?'count':
      /\b(empresas|empleadores)\b/.test(question)?'companies':'opportunities'
  };
}
export function analyzePublicRadar(availableJobs,query,snapshotAt){
  const plan=planPublicRadarQuery(query);
  const clock=validTime(snapshotAt);
  const candidates=(Array.isArray(availableJobs)?availableJobs:[]).slice(0,6500)
    .filter(j=>j && typeof j==='object' && https(j.source_url));
  const rules=domainRules.filter(d=>plan.topics.includes(d.name));
  const matchingTopics=candidates.filter(j=>{
    if(plan.unsupported_topic)return false;
    if(!rules.length)return true;
    // Match actual occupational evidence; a broad classification alone is
    // not evidence that a position specifically requires Python or GIS.
    const hay=plain([j.title,j.company_industry,(j.topics||[]).join(' '),j.search_scope,j.sector].join(' '));
    return rules.some(d=>d.match.test(hay));
  });
  const filteredBeforeDate=matchingTopics.filter(j=>
    (!plan.remote_only||j.remote_mode==='REMOTE')&&
    (!plan.confirmed_argentina_only||j.argentina_eligible==='YES')&&
    (!plan.spanish_requirement||j.work_language==='ES')&&
    (!plan.listing_spanish_only||j.listing_language==='ES')
  );
  const dateCoverage={
    con_fecha_publicacion:filteredBeforeDate.filter(j=>validTime(j.published_at)!==null).length,
    sin_fecha_publicacion:filteredBeforeDate.filter(j=>validTime(j.published_at)===null).length
  };
  const periodStart=clock&&plan.publication_window_hours?clock-plan.publication_window_hours*3600000:null;
  const selected=filteredBeforeDate.filter(j=>{
    if(!plan.publication_window_hours)return true;
    const p=validTime(j.published_at);
    return p!==null && periodStart!==null && p>=periodStart && p<=clock;
  });
  const ranked=selected.map(j=>{
    const published=validTime(j.published_at);
    const quality=Number.isFinite(Number(j.score))?Math.max(0,Math.min(100,Number(j.score))):0;
    const score=quality+(j.argentina_eligible==='YES'?12:0)+(j.remote_mode==='REMOTE'?5:0)+
      (published!==null && clock!==null && published<=clock && published>=clock-7*86400000?3:0);
    return {j,score};
  }).sort((a,b)=>b.score-a.score||String(a.j.source_url).localeCompare(String(b.j.source_url)));
  const byCompany=new Map();
  for(const j of selected){
    const name=String(j.company||'Empresa no informada').slice(0,100);
    byCompany.set(name,(byCompany.get(name)||0)+1);
  }
  const companies=[...byCompany].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0]))
    .slice(0,10).map(([empresa,avisos_en_captura])=>({empresa,avisos_en_captura}));
  const cautions=[
    'Los conteos corresponden al snapshot público consultado, no al total de vacantes del mercado ni a vacantes necesariamente abiertas.',
    'Solo argentina_eligible=YES confirma elegibilidad en el registro; UNKNOWN no se debe convertir en YES.',
    'Idioma del aviso y requisito de idioma laboral son campos diferentes.'
  ];
  if(plan.publication_window_hours)cautions.push(
    'El período se calcula desde generated_at del snapshot y por fecha published_at. No prueba qué avisos fueron detectados por primera vez; las publicaciones sin fecha quedan excluidas.'
  );
  if(plan.publication_window_hours && periodStart===null)cautions.push('Sin timestamp válido del snapshot no es posible calcular el período: conteo temporal no comprobable.');
  if(plan.remote_only && !plan.confirmed_argentina_only)cautions.push('REMOTO no demuestra que se pueda trabajar desde Argentina.');
  if(plan.spanish_requirement)cautions.push('Se incluyen solo requisitos work_language=ES explícitos; avisos en español sin requisito declarado no son suficientes.');
  if(plan.unsupported_topic)cautions.push('El tema '+plan.unsupported_topic+' no tiene filtro determinista soportado. La consulta no representa un conteo de vacantes para esa tecnología.');
  if(selected.length===0)cautions.push('Ninguna vacante satisface los filtros observables. No agregar puestos ajenos para completar una lista.');
  return {
    plan,
    summary:{
      snapshot_generado:clock!==null?new Date(clock).toISOString():'No disponible',
      total_avisos_con_url_en_captura:candidates.length,
      coincidencias_tematicas:matchingTopics.length,
      candidatos_antes_de_fecha:filteredBeforeDate.length,
      cobertura_fecha_de_candidatos:dateCoverage,
      periodo_inicio:periodStart!==null?new Date(periodStart).toISOString():null,
      coincidencias_filtro:selected.length,
      remotos_en_resultados:selected.filter(j=>j.remote_mode==='REMOTE').length,
      elegibilidad_argentina_confirmada_en_resultados:selected.filter(j=>j.argentina_eligible==='YES').length,
      trabajo_espanol_explicito_en_resultados:selected.filter(j=>j.work_language==='ES').length,
      empresas_en_resultados:companies,
      resultados_mostrados:Math.min(8,ranked.length),
      cautelas:cautions
    },
    selectedJobs:ranked.slice(0,8).map(x=>x.j)
  };
}


/* Query a verified pair of PUBLIC snapshots. Absence does not establish closure. */
export function analyzePublicRadarChanges(delta,currentJobs,query,currentGeneratedAt){
  const plan=planPublicRadarQuery(query);
  if(!plan.comparison_intent)return null;
  const unavailable=reason=>({
    available:false,comparison_intent:plan.comparison_intent,
    unavailable_reason:reason,
    caution:'No hay dos capturas públicas comparables; no inferir vacantes nuevas o cerradas.',
    selectedJobs:[]
  });
  if(!delta||delta.schema_version!==1||delta.comparison_type!=='consecutive_public_snapshots')
    return unavailable('Comparación entre capturas todavía no publicada');
  if(delta.current_generated_at!==currentGeneratedAt)
    return unavailable('La comparación no corresponde a la última captura publicada');
  if(delta.available!==true)
    return unavailable(String(delta.unavailable_reason||'Captura anterior no disponible').slice(0,140));
  const previous=Date.parse(delta.previous_generated_at),current=Date.parse(delta.current_generated_at);
  if(!Number.isFinite(previous)||!Number.isFinite(current)||previous>=current)
    return unavailable('Fechas de captura inválidas');
  const all=Array.isArray(currentJobs)?currentJobs:[];
  const newly=Array.isArray(delta.new_jobs)?delta.new_jobs:null;
  const missing=Array.isArray(delta.no_longer_observed_jobs)?delta.no_longer_observed_jobs:null;
  const counts=[delta.current_count,delta.previous_count,delta.newly_observed_count,delta.no_longer_observed_count,delta.continuing_count];
  if(!newly||!missing||counts.some(n=>!Number.isInteger(n)||n<0)||
     delta.current_count!==all.length||
     delta.newly_observed_count+delta.continuing_count!==delta.current_count||
     delta.no_longer_observed_count+delta.continuing_count!==delta.previous_count||
     newly.length!==delta.newly_observed_count||missing.length!==delta.no_longer_observed_count)
    return unavailable('Los conteos de ambas capturas no son coherentes');
  const allIds=new Set(all.map(x=>x.id)),newIds=new Set(newly.map(x=>x.id)),goneIds=new Set(missing.map(x=>x.id));
  if(allIds.size!==all.length||newIds.size!==newly.length||goneIds.size!==missing.length||
     newly.some(x=>!allIds.has(x.id))||missing.some(x=>allIds.has(x.id)))
    return unavailable('Inconsistencia entre identificadores de avisos');
  const kind=plan.comparison_intent;
  const group=kind==='no_longer_observed'?missing:
    kind==='continuing'?all.filter(x=>!newIds.has(x.id)):newly;
  const analysis=analyzePublicRadar(group,query,currentGeneratedAt);
  return {
    available:true,comparison_intent:kind,
    previous_generated_at:delta.previous_generated_at,
    current_generated_at:delta.current_generated_at,
    prev_total:delta.previous_count,current_total:delta.current_count,
    nuevos_observados:delta.newly_observed_count,
    ya_no_observados:delta.no_longer_observed_count,
    presentes_en_ambas:delta.continuing_count,
    coincidencias_con_filtros:analysis.summary.coincidencias_filtro,
    empresas_en_resultados:analysis.summary.empresas_en_resultados,
    cautelas:[
      'Se comparan sólo dos capturas consecutivas, no una serie histórica completa.',
      'Nuevo en la captura no prueba primera publicación; pudo reaparecer.',
      'Ausente de la última captura NO significa vacante cerrada.',
      'Cambios en cobertura de fuentes, ranking o identificadores pueden modificar la muestra.',
      ...analysis.summary.cautelas.filter(x=>!x.includes('período')&&!x.includes('published_at'))
    ],
    selectedJobs:analysis.selectedJobs
  };
}
