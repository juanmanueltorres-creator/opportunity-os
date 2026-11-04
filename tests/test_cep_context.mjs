import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
const base=new URL('../site/',import.meta.url);
const data=JSON.parse(readFileSync(new URL('cep-provincial-2022.json',base),'utf8'));
const src=readFileSync(new URL('cep-context.js',base),'utf8');
const html=readFileSync(new URL('index.html',base),'utf8');
const cfg=JSON.parse(readFileSync(new URL('vercel.json',base),'utf8'));
const metric=(rows,name)=>rows.reduce((s,r)=>s+r[name],0);

test('source metadata, grain and no present-day hiring claims',()=>{
  assert.equal(data.schema_version,1);
  assert.equal(data.reference_year,2022);
  assert.equal(data.provinces,24);
  assert.equal(data.source_rows,98924);
  assert.match(data.catalog_url,/^https:\/\/datos\.gob\.ar\//);
  assert.match(data.source_url,/^https:\/\/cdn\.produccion\.gob\.ar\//);
  assert.match(data.unit,/no empresas únicas ni vacantes/i);
  assert.match(html,/\/cep-context\.css/);
  assert.match(html,/\/cep-context\.js/);
  assert.match(src,/NO son datos de contratación actual/i);
});
test('unique province-sector entries, reviewed 2022 aggregate values',()=>{
  assert.equal(data.rows.length,476);
  assert.equal(new Set(data.rows.map(r=>r.province)).size,24);
  assert.equal(new Set(data.rows.map(r=>r.province+'|'+r.code)).size,data.rows.length);
  for(const row of data.rows){
    assert.match(row.code,/^[A-U]$/);
    assert.ok(Number.isSafeInteger(row.jobs)&&row.jobs>=0);
    assert.ok(Number.isSafeInteger(row.establishments)&&row.establishments>=0);
  }
  assert.equal(metric(data.rows,'jobs'),6595449);
  assert.equal(metric(data.rows,'establishments'),715377);
});
test('province and mining-sector comparisons are based on source, not vacancy feed',()=>{
  const cordoba=data.rows.filter(r=>r.province==='Córdoba');
  const mining=data.rows.filter(r=>r.code==='B');
  const cordobaMining=cordoba.filter(r=>r.code==='B');
  assert.ok(cordoba.length>15);
  assert.ok(metric(cordoba,'jobs')>metric(cordobaMining,'jobs'));
  assert.ok(metric(mining,'jobs')>=metric(cordobaMining,'jobs'));
  assert.ok(metric(data.rows,'jobs')>metric(cordoba,'jobs'));
  assert.ok(!src.includes('jobs.json'));
  assert.ok(!src.includes('localStorage'));
});
test('CSP allows static official data and keeps private sources constrained',()=>{
  const csp=cfg.headers[0].headers.find(h=>h.key==='Content-Security-Policy')?.value||'';
  assert.match(csp,/connect-src 'self' https:\/\/raw\.githubusercontent\.com/);
  assert.match(csp,/script-src 'self'/);
  assert.doesNotMatch(csp,/connect-src\s+\*/);
});
