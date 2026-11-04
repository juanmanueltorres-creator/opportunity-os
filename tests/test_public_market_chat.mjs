import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const base=new URL('../site/',import.meta.url);
const html=readFileSync(new URL('index.html',base),'utf8');
const front=readFileSync(new URL('public-chat.js',base),'utf8');
const guide=readFileSync(new URL('market-explorer.js',base),'utf8');
const hub=readFileSync(new URL('workspace-hub.js',base),'utf8');
const security=JSON.parse(readFileSync(new URL('vercel.json',base),'utf8'));
const market=JSON.parse(readFileSync(new URL('market-context-2026.json',base),'utf8'));
const companies=JSON.parse(readFileSync(new URL('public-company-guides-2026.json',base),'utf8'));
const {default:handler}=await import(new URL('api/chat.js',base));

const run=async(method,body,headers={})=>{
  const res={statusCode:200,headers:{},setHeader(k,v){this.headers[k]=v;},end(v){this.body=JSON.parse(v);}};
  await handler({method,body,headers:{host:'example.vercel.app',...headers}},res);
  return res;
};

test('public market aggregates are sourced, dated and not mislabelled vacancies',()=>{
  assert.equal(market.schema_version,1);
  assert.equal(market.figures.length,4);
  assert.ok(market.scope_note.includes('distintos'));
  const mining=market.figures.find(x=>x.id==='direct_mining');
  const commerce=market.figures.find(x=>x.id==='commerce_services');
  assert.equal(mining.value,39698);
  assert.equal(mining.period,'2026-01');
  assert.equal(commerce.value,4203016);
  assert.equal(commerce.period,'2025');
  for(const item of market.figures)assert.match(item.source_url,/^https:\/\//);
  assert.equal(companies.schema_version,1);
  assert.ok(companies.targets.length>=12);
  for(const c of companies.targets){
    assert.match(c.careers_url,/^https:\/\//);
    assert.ok(c.caution.length>20);
  }
  assert.equal(new Set(companies.targets.map(x=>x.id)).size,companies.targets.length);
});

test('the integrated chat has an evidence-only server endpoint and public-first UI',()=>{
  assert.match(html,/src="\/public-chat\.js" defer/);
  assert.match(html,/src="\/market-explorer\.js" defer/);
  assert.match(html,/src="\/public-chat\.css"/); // style is loaded in markup
  assert.match(front,/fetch\('\/api\/chat'/);
  assert.match(front,/textContent=text/);
  assert.match(front,/no se guarda en Opportunity OS/i);
  assert.doesNotMatch(front,/GEMINI_API_KEY|generativelanguage\.googleapis\.com/);
  assert.match(hub,/sections:\[orientation,publicChat\]/);
  assert.match(hub,/sections:\[marketLearning,cep,territorial,sources\]/);
  assert.match(guide,/Abrir mapa Leaflet/);
  assert.match(guide,/tile\.openstreetmap\.org/);
  const csp=security.headers[0].headers.find(x=>x.key==='Content-Security-Policy').value;
  assert.match(csp,/script-src 'self'/);
  assert.match(csp,/img-src 'self' data: https:\/\/tile\.openstreetmap\.org/);
});

test('server GET is safe and POST is disabled without server-side opt-in',async()=>{
  for(const name of ['GEMINI_API_KEY','OPPORTUNITY_GEMINI_ENABLED','GEMINI_FREE_TIER_CONFIRMED'])delete process.env[name];
  let res=await run('GET',null);
  assert.equal(res.statusCode,200);
  assert.equal(res.body.enabled,false);
  assert.equal(res.body.stores_messages,false);
  res=await run('POST',{message:'Compará comercio y minería'});
  assert.equal(res.statusCode,503);
  assert.match(res.body.error,/deshabilitado/);
  res=await run('POST',{message:'Compará comercio y minería'},{origin:'https://attacker.invalid'});
  assert.equal(res.statusCode,403);
});

test('server calls Gemini only with selected public evidence and bounded text',async()=>{
  const original=globalThis.fetch;
  process.env.GEMINI_API_KEY='test-not-a-real-key';
  process.env.OPPORTUNITY_GEMINI_ENABLED='true';
  process.env.GEMINI_FREE_TIER_CONFIRMED='true';
  let sent;
  globalThis.fetch=async(input,opts)=>{
    const u=String(input);
    if(u.includes('radar-public/jobs.json'))return {
      ok:true,status:200,headers:{get:()=>null},json:async()=>({
        generated_at:'2026-11-04T18:00:00-03:00',atlas:[
          {id:'t1',company:'Demostración',title:'Analista de datos GIS',
            source_url:'https://example.org/empleo/1',remote_mode:'REMOTE',
            argentina_eligible:'UNKNOWN',work_language:'UNKNOWN',listing_language:'ES',
            track:'gis_geoscience',location:'Argentina',published_at:'2026-11-04'}
        ]})
    };
    if(u.includes('generativelanguage.googleapis.com')){
      sent=JSON.parse(opts.body);
      assert.equal(opts.headers['x-goog-api-key'],'test-not-a-real-key');
      return {ok:true,status:200,json:async()=>({
        candidates:[{content:{parts:[{text:'El aviso de muestra requiere verificar elegibilidad [S1].'}]}}]
      })};
    }
    throw Error('Unexpected external request '+u);
  };
  try{
    const res=await run('POST',{message:'¿Hay empleo remoto de GIS en Argentina?'});
    assert.equal(res.statusCode,200);
    assert.match(res.body.answer,/verificar elegibilidad/);
    assert.equal(res.body.feed_available,true);
    assert.ok(res.body.sources.length>0);
    const payload=JSON.stringify(sent);
    assert.match(payload,/CONTEXTO_JSON/);
    assert.match(payload,/argentina_elegible/);
    assert.match(payload,/UNKNOWN/);
    assert.ok(payload.includes('Demostración'));
    assert.ok(!payload.includes('GEMINI_API_KEY'));
    assert.equal(res.body.scope,'Fuentes públicas · no incluye Excel, contactos ni historial privado');
  }finally{
    globalThis.fetch=original;
    delete process.env.GEMINI_API_KEY;
    delete process.env.OPPORTUNITY_GEMINI_ENABLED;
    delete process.env.GEMINI_FREE_TIER_CONFIRMED;
  }
});
