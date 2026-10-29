import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const html = readFileSync(new URL('../site/index.html', import.meta.url), 'utf8');

test('Empresas is the primary three-column workspace with explicit modes', () => {
  assert.match(html, /class="company-workspace"/);
  assert.equal((html.match(/class="workspace-column/g) ?? []).length, 3);
  assert.match(html, /Trabajo ahora · Español/);
  assert.match(html, /Explorar todo/);
  assert.match(html, /id="companyRows"/);
  assert.match(html, /id="companyDetail"/);
  assert.match(html, /id="cards"/);
});

test('public workspace does not expose manual application tracking controls', () => {
  assert.doesNotMatch(html, /Mi seguimiento local/);
  assert.doesNotMatch(html, /Postulé/);
  assert.doesNotMatch(html, /Descartar/);
});
