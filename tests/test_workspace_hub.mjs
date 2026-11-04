import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const base=new URL('../site/',import.meta.url);
const js=readFileSync(new URL('workspace-hub.js',base),'utf8');
const css=readFileSync(new URL('workspace-hub.css',base),'utf8');
const html=readFileSync(new URL('index.html',base),'utf8');

test('public orientation plus four existing destinations reuse working panels',()=>{
  for(const id of ["orientacion","buscar","empresas","seguimiento","datos"])assert.ok(js.includes(id+':{label:'),id);
  for(const sel of [".quick-panel",".clarity-routes","#atlas-empresas","#discovery-targets",".tracker-panel","#contexto-productivo",".today",".layout",".sources"])assert.ok(js.includes(sel),sel);
  assert.match(html,/src="\/workspace-hub\.js" defer/);
  assert.match(html,/href="\/workspace-hub\.css"/);
  assert.ok(html.indexOf('/workspace-hub.js')>html.indexOf('/clarity.js'));
  assert.match(css,/\.hub-tab\.active/);
  assert.match(css,/\[hidden\]/);
});
test('private Excel import funnels through existing tracker and atlas event',()=>{
  assert.match(js,/tracker\.querySelector\('#trackerImport'\)\?\.click\(\)/);
  assert.match(js,/opportunity:local-file/);
  assert.ok(!js.includes('localStorage.setItem'));
  assert.ok(!js.includes('/api/'));
  assert.ok(!js.includes('fetch('));
  assert.ok(!js.includes('mailto:'));
});
test('keyboard and deep linking work without recreating data',()=>{
  assert.match(js,/ArrowRight/);
  assert.match(js,/ArrowLeft/);
  assert.match(js,/hashchange/);
  assert.match(js,/popstate/);
  assert.match(js,/replaceState/);
  assert.match(js,/orientacion/);
  assert.match(js,/El seguimiento personal es opcional/);
  assert.match(js,/view!==\x27seguimiento\x27/);
});

test('compass drives existing views and home defaults to public orientation',()=>{
  assert.match(js,/routeHash\(\)\|\|'orientacion'/);
  assert.match(js,/opportunity:workspace-go/);
  assert.match(js,/document\.getElementById\('clear'\)\?\.click\(\)/);
  assert.match(js,/companyMode='discovery'/);
  assert.ok(!js.includes("localStorage.setItem"));
});
