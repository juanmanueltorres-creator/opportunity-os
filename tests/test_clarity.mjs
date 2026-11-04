import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const root=new URL('../site/',import.meta.url);
const data=JSON.parse(readFileSync(new URL('discovery-companies-2026.json',root),'utf8'));
const html=readFileSync(new URL('index.html',root),'utf8');
const clarity=readFileSync(new URL('clarity.js',root),'utf8');
const atlas=readFileSync(new URL('company-atlas.js',root),'utf8');

test('every published company is sourced and region explicit',()=>{
  assert.equal(data.schema_version,1);
  assert.equal(data.reviewed_on,'2026-11-04');
  assert.ok(data.companies.length>=30);
  const pba=data.companies.filter(x=>x.province==='Buenos Aires');
  const caba=data.companies.filter(x=>x.province==='CABA');
  assert.ok(pba.length>=10);
  assert.ok(caba.length>=10);
  assert.ok(!pba.some(x=>x.city.toUpperCase().includes('CABA')));
  const seen=new Set();
  for(const x of data.companies){
    assert.ok(x.name && x.activity && x.city && x.province);
    assert.ok(/^https:\/\/cessi\.org\.ar\/directorio-de-empresas\/(\?pagina=\d+)?$/.test(x.source_url));
    assert.ok(!seen.has(x.name.toLowerCase()));seen.add(x.name.toLowerCase());
    assert.equal('email' in x,false);
    assert.equal('vacancy' in x,false);
  }
});
test('new discovery is separate from private Excel and no outreach sent',()=>{
  assert.match(html,/href="\/clarity\.css"/);
  assert.match(html,/src="\/clarity\.js"/);
  assert.match(clarity,/Objetivo para investigar/);
  assert.match(clarity,/Tu Excel no se modifica/);
  assert.match(clarity,/No se envían postulaciones ni contactos/);
  assert.doesNotMatch(clarity,/fetch\(['"]https:\/\/[^'"]+\/api/);
  assert.doesNotMatch(clarity,/navigator\.sendBeacon|XMLHttpRequest/);
});
test('province attribution remains evidence-only and shows missing',()=>{
  assert.match(atlas,/Argentina · sin provincia/);
  assert.match(atlas,/province==='__UNKNOWN__'/);
  assert.match(atlas,/Buenos Aires/);
  assert.match(atlas,/CABA/);
  assert.match(atlas,/Ver las 24 provincias/);
  assert.match(atlas,/Datos pendientes de verificar/);
});
