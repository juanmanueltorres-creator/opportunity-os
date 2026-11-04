import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const src = readFileSync(new URL('../site/company-atlas.js', import.meta.url), 'utf8');
const pick = (start, end) => {
  const a = src.indexOf(start);
  const b = src.indexOf(end, a + start.length);
  assert.ok(a >= 0 && b > a, 'Parser section present: ' + start);
  return src.slice(a, b);
};

// Test just the pure parsing logic, without loading an actual CV, contact list or browser storage.
const parsing = new Function(
  pick('  const PROVINCES =', '  const SECTION =')
  + pick('  const $ =', '  let records=')
  + pick('  function countryFrom', '  function addRecords')
  + 'return { asRows, countryFrom, provinceFrom, stateFrom, sectorFrom };'
)();

test('countries and provinces are not fabricated from unknown places', () => {
  assert.equal(parsing.countryFrom(''), 'No informado');
  assert.equal(parsing.countryFrom('Córdoba (domicilio legal)'), 'Argentina');
  assert.equal(parsing.countryFrom('México'), 'México');
  assert.equal(parsing.countryFrom('Uruguay'), 'Uruguay');
  assert.equal(parsing.provinceFrom('Argentina (varias provincias)'), '');
  assert.equal(parsing.provinceFrom('Oncativo / Córdoba'), 'Córdoba');
});

test('prior outreach is not interpreted as no contact', () => {
  assert.equal(parsing.stateFrom('CONTACTO PREVIO'), 'sent');
  assert.equal(parsing.stateFrom('ENVIADO 29-10'), 'sent');
  assert.equal(parsing.stateFrom('REPLIED'), 'reply');
  assert.equal(parsing.stateFrom('APPLIED'), 'applied');
  assert.equal(parsing.stateFrom('SIN CONTACTAR'), 'pending');
  assert.equal(parsing.stateFrom('DRAFT'), 'draft');
});

test('reads EMPRESAS_400, Unificado and federal directorio headers', () => {
  const companies = parsing.asRows([
    ['ID global','Bloque','País','Rank local','Empresa','Sector / área','Estado actual','Sitio / fuente'],
    [1,'ARGENTINA','Argentina',1,'Empresa Demo Minera','Minería','ENVIADO 29-10','https://example.org/']
  ], 'EMPRESAS_400');
  assert.equal(companies.length, 1);
  assert.equal(companies[0].sector, 'Minería');
  assert.equal(companies[0].country, 'Argentina');
  assert.equal(companies[0].state, 'sent');

  const unified = parsing.asRows([
    ['ID original','Empresa / entidad','Estado actual / Gmail','Ubicación','Hipótesis / rol'],
    [1,'Empresa Geo Ejemplo','CONTACTO PREVIO','Córdoba (domicilio legal)','GIS / geoespacial'],
    [2,'Proyecto sin domicilio','POR INVESTIGAR','','Soporte de aplicaciones']
  ],'Unificado');
  assert.equal(unified.length, 2);
  assert.equal(unified[0].province,'Córdoba');
  assert.equal(unified[0].state,'sent');
  assert.equal(unified[1].country,'No informado');

  const federal = parsing.asRows([
    ['#','Prioridad','Nivel','Provincia','Municipio','Organismo','Área / Dependencia','Estado','Fuente URL'],
    [1,'A','Provincial','Santa Fe','','Secretaría de Turismo Ejemplo','Turismo','YA ENVIADO','https://example.org/'],
    [2,'A','Provincial','Córdoba','','Secretaría de Turismo Ejemplo','Turismo','SIN CONTACTAR','https://example.org/']
  ],'Directorio');
  assert.equal(federal.length,2);
  assert.notEqual(federal[0].key,federal[1].key,'same-name agencies from different provinces must remain separate');
  assert.equal(federal[0].type,'Organismo');
  assert.equal(federal[0].province,'Santa Fe');
  assert.equal(federal[0].state,'sent');
});

test('does not accept unsafe source links', () => {
  const data=parsing.asRows([
    ['ID original','Empresa / entidad','Estado actual / Gmail','Web fuente'],
    [1,'Organización de ejemplo','PENDIENTE','javascript:alert(1)']
  ],'Unificado');
  assert.equal(data[0].source,null);
});
