import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const root=new URL('../site/',import.meta.url);
const file=(name)=>readFileSync(new URL(name,root),'utf8');
const html=file('index.html');
const unified=file('unified-workspace.js');
const atlas=file('company-atlas.js');
const tracking=file('enhancements.js');
const regional=file('clarity.js');

test('unified experience loads last and reuses existing components',()=>{
  assert.match(html,/href="\/unified-workspace\.css"/);
  assert.match(html,/src="\/unified-workspace\.js" defer/);
  const scripts=['enhancements.js','company-atlas.js','cep-context.js','clarity.js','unified-workspace.js'];
  const positions=scripts.map(s=>html.indexOf('src="/'+s+'"'));
  assert.ok(positions.every(x=>x!==-1));
  assert.deepEqual([...positions].sort((a,b)=>a-b),positions);
  for(const part of ['.quick-panel','#atlas-empresas','#discovery-targets','#contexto-productivo','.tracker-panel','.clarity-routes'])
    assert.ok(unified.includes(part));
});
test('directory views preserve private/public/historical boundaries',()=>{
  assert.match(unified,/unified-view-private/);
  assert.match(unified,/unified-view-discovery/);
  assert.match(unified,/unified-view-context/);
  assert.match(unified,/role','tabpanel'/);
  assert.match(unified,/aria-selected/);
  assert.match(unified,/Datos de empleo y establecimientos de 2022/);
  assert.match(unified,/no se suman a tus contactos ni representan vacantes abiertas/);
  assert.match(unified,/atlas\.insertBefore\(wrapper,sourcePanel\)/);
  assert.doesNotMatch(unified,/fetch\(|new XMLHttpRequest|navigator\.sendBeacon/);
});
test('national default and opt-in work location are distinct from eligibility',()=>{
  assert.match(regional,/name:'Todo el país',where:'Argentina'/);
  assert.match(unified,/activeRegion='Todo el país'/);
  assert.match(unified,/Remoto describe un aviso, no la sede de una empresa/);
  assert.match(unified,/f_WT/);
  assert.match(unified,/español|Spanish listing only/i);
});
test('Excel flows into atlas and tracker once without bidirectional recursion',()=>{
  assert.match(tracking,/async function importFile\(file, forwardToAtlas = true\)/);
  assert.match(tracking,/if \(forwardToAtlas\) window\.dispatchEvent/);
  assert.match(tracking,/opportunity:atlas-file/);
  assert.match(tracking,/await importFile\(file, false\)/);
  assert.match(atlas,/async function importFiles\(files, fromTracker = false\)/);
  assert.match(atlas,/if\(!fromTracker && successful\.length\)/);
  assert.match(atlas,/opportunity:atlas-file/);
  assert.match(atlas,/await importFiles\(\[event\.detail\.file\],true\)/);
});
test('unification is presentation-only: no automatic sends or secret paths',()=>{
  assert.doesNotMatch(unified,/mailto:|sendEmail|autopost|auto.?apply|supabase|token=|Bearer /i);
  assert.match(unified,/Un mismo archivo puede alimentar este resumen y el directorio/);
  assert.match(unified,/unifiedRadar/);
  assert.match(unified,/unifiedCompanies/);
  assert.match(unified,/Ver distribución territorial de los avisos/);
});
