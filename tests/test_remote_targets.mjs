import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const root=new URL('../site/',import.meta.url);
const src=n=>readFileSync(new URL(n,root),'utf8');
const data=JSON.parse(src('remote-targets-2026.json'));
const js=src('remote-targets.js');
const html=src('index.html');
test('Five targets have public recruitment evidence and no invented salary/headcount',()=>{
  assert.equal(data.schema_version,1);
  assert.equal(data.reviewed_on,'2026-11-04');
  assert.equal(data.targets.length,5);
  assert.equal(new Set(data.targets.map(x=>x.name)).size,5);
  assert.ok(data.targets.every(x=>x.remote&&x.rolesUrl.startsWith('https://')&&x.evidenceUrl.startsWith('https://')));
  assert.ok(data.targets.every(x=>x.headcountArgentina===null));
  assert.ok(data.targets.some(x=>x.name.includes('RWS')&&x.pay.includes('8/h')));
  assert.ok(data.targets.some(x=>x.name.includes('Welo')&&x.pay.includes('4/h')));
  assert.ok(data.targets.some(x=>/inglés B2|B2/.test(x.english)));
});
test('Freelance proposals are scoped and need proof of gaps',()=>{
  assert.equal(data.services.length,4);
  assert.equal(new Set(data.services.map(x=>x.id)).size,4);
  assert.ok(data.services.every(x=>x.target&&x.deliverable&&x.evidence&&x.next));
  assert.ok(data.services.some(x=>x.id==='landing'));
  assert.match(js,/No encontré web propia/);
  assert.match(js,/no es lo mismo que afirmar/);
});
test('Remote is default; main source feed and private tracker are unchanged',()=>{
  assert.match(html,/href="\/remote-targets\.css"/);
  assert.match(html,/src="\/remote-targets\.js" defer/);
  assert.match(js,/mode\.value='REMOTE'/);
  assert.match(js,/mode\.dispatchEvent\(new Event\('input'/);
  assert.match(js,/clear\.addEventListener\('click'/);
  assert.doesNotMatch(js,/localStorage|sessionStorage|sendBeacon|fetch\(.*method|POST|API_KEY/);
  assert.ok(html.indexOf('src="/workspace-hub.js"') < html.indexOf('src="/remote-targets.js"'));
});
