import test from 'node:test';
import assert from 'node:assert/strict';
import {analyzePublicRadar,analyzePublicRadarChanges,planPublicRadarQuery} from '../site/api/radar-query.js';

const at='2026-11-05T20:00:00Z';
const row=(id,title,published_at,rest={})=>({
  id,company:'Compañía '+id,title,published_at,
  source_url:'https://example.org/jobs/'+id,score:80,
  remote_mode:'REMOTE',argentina_eligible:'YES',
  work_language:'UNKNOWN',listing_language:'ES',topics:[],...rest
});
const jobs=[
  row('uno','Analista GIS','2026-11-05T18:00:00Z',{company:'Geo A',work_language:'ES'}),
  row('dos','GIS support','2026-11-05T12:00:00Z',{company:'Geo A',argentina_eligible:'UNKNOWN'}),
  row('tres','ArcGIS specialist','2026-11-04T12:00:00Z',{company:'Geo B'}),
  row('cuatro','QGIS analyst','2026-10-27T12:00:00Z',{company:'Geo B'}),
  row('cinco','Python developer','2026-11-05T16:00:00Z',{company:'Tech'}),
  row('seis','GIS engineer',null,{company:'Geo C'}),
  row('siete','GIS architect','2026-11-05T16:00:00Z',{company:'Geo C',argentina_eligible:'NO'}),
  row('ocho','GIS engineer','2026-11-05T16:00:00Z',{company:'Geo D',remote_mode:'ONSITE'}),
  row('nueve','Backend Python','2026-11-05T17:00:00Z',{company:'Tech',work_language:'EN'}),
];
test('strict count of recent remotely eligible GIS positions uses published_at only',()=>{
  const r=analyzePublicRadar(jobs,'¿Cuántas vacantes remotas de GIS aceptan Argentina en las últimas 24 horas?',at);
  assert.equal(r.summary.coincidencias_filtro,1);
  assert.equal(r.selectedJobs[0].id,'uno');
  assert.equal(r.summary.cobertura_fecha_de_candidatos.sin_fecha_publicacion,1);
  assert.equal(r.summary.periodo_inicio,'2026-11-04T20:00:00.000Z');
  assert.match(r.summary.cautelas.join(' '),/No prueba qué avisos fueron detectados por primera vez/);
});
test('week company counts are deterministic, using only documented publication dates',()=>{
  const r=analyzePublicRadar(jobs,'¿Qué empresas publicaron puestos GIS esta semana?',at);
  assert.equal(r.plan.publication_window_hours,168);
  assert.equal(r.summary.coincidencias_filtro,5);
  assert.deepEqual(r.summary.empresas_en_resultados.map(x=>[x.empresa,x.avisos_en_captura]),[
    ['Geo A',2],['Geo B',1],['Geo C',1],['Geo D',1]
  ]);
});
test('language filters never infer language requirements from listing text',()=>{
  let r=analyzePublicRadar(jobs,'¿Hay trabajo en español de GIS?',at);
  assert.deepEqual(r.selectedJobs.map(j=>j.id),['uno']);
  r=analyzePublicRadar(jobs,'¿Hay avisos en español de Python?',at);
  assert.equal(r.summary.coincidencias_filtro,2);
});
test('compass appended text is never interpreted as a hard requirement',()=>{
  const plan=planPublicRadarQuery('¿Qué empresas publicaron GIS?\nContexto elegido en la brújula (preferencias del visitante, no evidencia): 100 % remoto · Argentina');
  assert.equal(plan.remote_only,false);
  assert.equal(plan.confirmed_argentina_only,false);
});
test('empty temporal results are honestly empty, and count is not invented',()=>{
  const r=analyzePublicRadar([row('x','GIS Analyst',null)],'¿Cuántos avisos de GIS desde ayer?',at);
  assert.equal(r.summary.coincidencias_filtro,0);
  assert.equal(r.summary.cobertura_fecha_de_candidatos.sin_fecha_publicacion,1);
  assert.equal(r.selectedJobs.length,0);
});
test('without a valid snapshot timestamp the time window never returns all-time jobs',()=>{
  const r=analyzePublicRadar(jobs,'¿Cuántos puestos GIS desde ayer?','malformed');
  assert.equal(r.summary.coincidencias_filtro,0);
  assert.match(r.summary.cautelas.join(' '),/Sin timestamp válido/);
});

test('explicit Python queries never count generic Java backend roles',()=>{
  const sample=[
    row('python','Python developer','2026-11-05T16:00:00Z'),
    row('java','Backend Java developer','2026-11-05T15:00:00Z')
  ];
  const r=analyzePublicRadar(sample,'¿Cuántas vacantes de Python hay?',at);
  assert.equal(r.summary.coincidencias_filtro,1);
  assert.equal(r.selectedJobs[0].id,'python');
});

test('unsupported explicit roles do not count the entire snapshot',()=>{
  const r=analyzePublicRadar(jobs,'¿Cuántas vacantes de soldador hay?',at);
  assert.equal(r.plan.unsupported_topic,'soldador');
  assert.equal(r.summary.coincidencias_filtro,0);
  assert.match(r.summary.cautelas.join(' '),/no tiene filtro determinista soportado/);
});

test('JavaScript is recognized as a supported technology rather than the entire snapshot',()=>{
  const sample=[
    row('js','JavaScript developer','2026-11-05T16:00:00Z'),
    row('py','Python developer','2026-11-05T16:00:00Z')
  ];
  const r=analyzePublicRadar(sample,'¿Cuántas vacantes de JavaScript hay?',at);
  assert.equal(r.summary.coincidencias_filtro,1);
  assert.equal(r.selectedJobs[0].id,'js');
});


test('new in previous comparison is not inferred from the posting date',()=>{
  const current=[row('new','GIS Analyst','2026-10-20T16:00:00Z'),row('old','Python developer','2026-11-05T16:00:00Z')];
  const delta={schema_version:1,comparison_type:'consecutive_public_snapshots',available:true,
    current_generated_at:at,previous_generated_at:'2026-11-04T20:00:00Z',
    current_count:2,previous_count:2,newly_observed_count:1,no_longer_observed_count:1,continuing_count:1,
    new_jobs:[current[0]],no_longer_observed_jobs:[row('gone','GIS Support',null)]};
  const r=analyzePublicRadarChanges(delta,current,'¿Qué vacantes nuevas de GIS aparecieron desde ayer?',at);
  assert.equal(r.available,true);
  assert.equal(r.coincidencias_con_filtros,1);
  assert.equal(r.nuevos_observados,1);
  assert.equal(r.selectedJobs[0].id,'new');
  assert.equal(planPublicRadarQuery('¿Qué vacantes nuevas de GIS aparecieron desde ayer?').publication_window_hours,null);
});
test('missing or stale delta cannot invent changed jobs',()=>{
  const current=[row('one','GIS Analyst',null)];
  const invalid=[null,{schema_version:1,comparison_type:'consecutive_public_snapshots',
    available:true,current_generated_at:'2020-01-01T00:00:00Z'}];
  for(const delta of invalid){
    const r=analyzePublicRadarChanges(delta,current,'¿Qué avisos nuevos hay?',at);
    assert.equal(r.available,false);
    assert.equal(r.selectedJobs.length,0);
  }
});
test('absence is observable but never a closed vacancy',()=>{
  const current=[row('present','GIS Analyst',null)],gone=row('gone','GIS Technician',null);
  const delta={schema_version:1,comparison_type:'consecutive_public_snapshots',available:true,
    current_generated_at:at,previous_generated_at:'2026-11-04T20:00:00Z',
    current_count:1,previous_count:1,newly_observed_count:1,no_longer_observed_count:1,continuing_count:0,
    new_jobs:current,no_longer_observed_jobs:[gone]};
  const r=analyzePublicRadarChanges(delta,current,'¿Qué avisos GIS desaparecieron?',at);
  assert.equal(r.available,true);
  assert.equal(r.coincidencias_con_filtros,1);
  assert.equal(r.selectedJobs[0].id,'gone');
  assert.match(r.cautelas.join(' '),/NO significa vacante cerrada/);
});
test('inconsistent counts or foreign IDs reject the comparison',()=>{
  const current=[row('present','GIS Analyst',null)];
  const delta={schema_version:1,comparison_type:'consecutive_public_snapshots',available:true,
    current_generated_at:at,previous_generated_at:'2026-11-04T20:00:00Z',
    current_count:1,previous_count:1,newly_observed_count:1,no_longer_observed_count:1,continuing_count:0,
    new_jobs:[row('outsider','GIS Analyst',null)],no_longer_observed_jobs:[row('gone','GIS Tech',null)]};
  const r=analyzePublicRadarChanges(delta,current,'¿Qué avisos nuevos GIS hay?',at);
  assert.equal(r.available,false);
  assert.equal(r.coincidencias_con_filtros,undefined);
});


test('companies that started posting are classified as a capture comparison',()=>{
  const plan=planPublicRadarQuery('¿Qué empresas comenzaron a publicar avisos desde la última captura?');
  assert.equal(plan.comparison_intent,'newly_observed');
  assert.equal(plan.publication_window_hours,null);
});


test('ordinary comparison between skills is not redirected into capture changes',()=>{
  const plan=planPublicRadarQuery('Compará ofertas de Python y GIS');
  assert.equal(plan.comparison_intent,null);
  assert.equal(plan.topics.length,2);
  assert.equal(planPublicRadarQuery('Compará capturas de ayer y hoy').comparison_intent,'summary');
});
test('summary includes both additions and disappearances for requested role',()=>{
  const current=[row('python','Python developer',at)];
  const gone=row('geo','GIS Technician','2026-11-04T15:00:00Z');
  const delta={schema_version:1,comparison_type:'consecutive_public_snapshots',available:true,
    current_generated_at:at,previous_generated_at:'2026-11-04T20:00:00Z',
    current_count:1,previous_count:1,newly_observed_count:1,no_longer_observed_count:1,continuing_count:0,
    new_jobs:current,no_longer_observed_jobs:[gone]};
  const summary=analyzePublicRadarChanges(delta,current,'¿Qué cambios hubo de GIS desde la captura anterior?',at);
  assert.equal(summary.available,true);
  assert.equal(summary.nuevos_filtrados,0);
  assert.equal(summary.ausentes_filtrados,1);
  assert.equal(summary.coincidencias_con_filtros,1);
  assert.equal(summary.selectedJobs[0].id,'geo');
  assert.equal(summary.selectedJobs[0].observation_change,'YA_NO_OBSERVADO');
});
test('public industry classification remains available in the new-observation filter',()=>{
  const current=[row('agzen','Product Designer',at,{company:'AgZen',company_industry:'agtech'})];
  const delta={schema_version:1,comparison_type:'consecutive_public_snapshots',available:true,
    current_generated_at:at,previous_generated_at:'2026-11-04T20:00:00Z',
    current_count:1,previous_count:0,newly_observed_count:1,no_longer_observed_count:0,continuing_count:0,
    new_jobs:current,no_longer_observed_jobs:[]};
  const results=analyzePublicRadarChanges(delta,current,'¿Qué vacantes nuevas de agro aparecieron?',at);
  assert.equal(results.coincidencias_con_filtros,1);
  assert.equal(results.selectedJobs[0].id,'agzen');
});
