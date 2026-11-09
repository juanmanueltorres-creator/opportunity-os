import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const base=new URL('../site/',import.meta.url);
const read=name=>readFileSync(new URL(name,base),'utf8');
const hub=read('workspace-hub.js');
const styles=read('workspace-hub.css');
const regional=read('clarity.js');

test('one nationwide search workflow with optional province and remote',()=>{
  assert.match(regional,/name:'Todo el país',where:'Argentina'/);
  assert.match(regional,/name:'Buenos Aires'/);
  assert.match(regional,/name:'CABA'/);
  assert.match(regional,/name:'Remoto'/);
  assert.match(regional,/name:'Córdoba'/);
  assert.match(hub,/chips\.insertAdjacentElement\('afterend',routes\)/);
  assert.match(hub,/hub-inline-routes/);
  assert.match(styles,/\.quick-panel>\.clarity-routes\.hub-inline-routes/);
  assert.match(hub,/quickLinks\?\.querySelectorAll\('a\[href\]'\)/);
  assert.match(hub,/f_WT','2'/);
  assert.match(hub,/hubToRadar/);
  assert.match(hub,/listing\.value='ES'/);
  assert.match(hub,/Spanish listing is not proof/);
});

test('company modes separate private records and public discovery',()=>{
  assert.match(hub,/companyMode='discovery'/);
  assert.match(hub,/companyMode='private'/);
  assert.match(hub,/companyMode!=='private'/);
  assert.match(hub,/companyMode!=='discovery'/);
  assert.match(hub,/hub-company-switch/);
  assert.match(hub,/opportunity:atlas-change/);
  assert.match(hub,/switchCompanies\(\)/);
  assert.match(styles,/\.hub-company-option\.active/);
});

test('preserve original hub privacy and one canonical import',()=>{
  assert.match(hub,/tracker\.querySelector\('#trackerImport'\)\?\.click\(\)/);
  assert.match(hub,/Sumar directorio adicional/);
  assert.doesNotMatch(hub,/localStorage\.setItem/);
  assert.doesNotMatch(hub,/sendBeacon|sendEmail|mailto:|fetch\(/);
  assert.match(hub,/La orientación, las vacantes y el directorio público funcionan sin Excel/);
  assert.match(hub,/El seguimiento personal es opcional/);
  assert.match(hub,/view!==\x27seguimiento\x27/);
});

test('search presets and recency controls preserve existing sources',()=>{
  const quick=read('enhancements.js');
  const html=read('index.html');
  for(const label of ['GIS / SIG','Minería / Geología','Python / Datos','Soporte N1','QGIS / Teledetección','Logística / Depósito','Atención al cliente']) {
    assert.ok(quick.includes(label),label);
  }
  assert.match(quick,/id="quickFreshness"/);
  assert.match(quick,/Últimos 7 días/);
  assert.match(quick,/&f_TPR=r/);
  assert.match(quick,/&fromage=/);
  assert.match(quick,/&sortBy=DD/);
  assert.match(quick,/Computrabajo requiere elegir/);
  assert.match(quick,/trabajo-de-trabajo-remoto-en-remoto/);
  assert.match(quick,/quick-keyword-list/);
  assert.match(html,/<option value="30" selected>Últimos 30 días/);
  assert.match(html,/Fecha de publicación no confirmada/);
  assert.match(html,/\$\('age'\)\.value='30'/);
});
