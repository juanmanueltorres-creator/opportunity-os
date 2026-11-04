import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const dir=new URL('../site/',import.meta.url);
const js=readFileSync(new URL('orientation-guide.js',dir),'utf8');
const css=readFileSync(new URL('orientation-guide.css',dir),'utf8');
const html=readFileSync(new URL('index.html',dir),'utf8');
const hub=readFileSync(new URL('workspace-hub.js',dir),'utf8');

test('public compass is loaded before the hub and is accessible without workbook',()=>{
  assert.match(html,/href="\/orientation-guide\.css"/);
  assert.match(html,/src="\/orientation-guide\.js" defer/);
  assert.ok(html.indexOf('/orientation-guide.js')<html.indexOf('/workspace-hub.js'));
  assert.match(js,/id='orientacion'/);
  assert.match(js,/aria-labelledby/);
  assert.ok(!js.includes('localStorage'));
  assert.ok(!js.includes('fetch('));
  assert.ok(!js.includes('GEMINI_API_KEY'));
  assert.ok(!js.includes('apiKey'));
  assert.match(css,/\.orientation-guide\[hidden\]/);
});

test('distinct public outcomes reuse the existing app and no new backend',()=>{
  for(const outcome of ['jobs','companies','freelance'])assert.match(js,new RegExp(outcome+':\\{label:'));
  for(const key of ['objetivo','area','modalidad'])assert.ok(js.includes(key));
  assert.match(js,/opportunity:workspace-go/);
  assert.match(hub,/companyMode='discovery'/);
  assert.match(hub,/opportunity:workspace-go/);
  assert.match(js,/URLSearchParams/);
  assert.match(js,/https:\/\/cessi\.org\.ar\/directorio-de-empresas\//);
});

test('orientation routes visitors to the embedded Gemini chat without exposing keys',()=>{
  assert.match(js,/document.getElementById\('chat'\)/);
  assert.match(js,/Preguntarle al chat de la web/);
  assert.match(js,/orientationScope/);
  assert.match(js,/ambito/);
  assert.match(html,/id="openGemini"/);
  assert.match(html,/no se comparte tu Excel ni ninguna clave de API/i);
  assert.ok(!js.includes('generativelanguage.googleapis.com'));
});
