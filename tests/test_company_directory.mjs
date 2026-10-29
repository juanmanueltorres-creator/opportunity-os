import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const require = createRequire(import.meta.url);
let directory;
try {
  directory = require('../site/company-directory.js');
} catch (error) {
  if (error.code !== 'MODULE_NOT_FOUND' || !error.message.includes('site/company-directory.js')) throw error;
}

function implementation() {
  assert.ok(directory, 'site/company-directory.js must export the public company directory model');
  return directory;
}

const vacancies = [
  {
    id: 'vacancy-1',
    company: 'Andes Energía',
    title: 'GIS Analyst',
    track: 'gis_geoscience',
    topics: ['gis', 'geology_mining'],
    company_industry: 'mining',
    location: 'Salta, Argentina',
    source_url: 'https://careers.example.com/jobs/1',
  },
  {
    id: 'vacancy-2',
    company: 'Andes Energía',
    title: 'Geospatial Engineer',
    track: 'software_ai',
    topics: ['software_data'],
    location: 'Remote',
    source_url: 'https://careers.example.com/jobs/2',
  },
  {
    id: 'vacancy-3',
    company: 'Delta Labs',
    title: 'Python Developer',
    track: 'software_ai',
    topics: ['software_data'],
    location: 'Argentina',
    source_url: 'https://jobs.example.org/3',
  },
  { id: 'vacancy-4', title: 'Unattributed role', source_url: 'https://jobs.example.org/4' },
];

test('companies are derived from named vacancies with real vacancy counts', () => {
  const companies = implementation().deriveCompanies(vacancies);

  assert.deepEqual(companies.map(({ name, vacancyCount }) => [name, vacancyCount]), [
    ['Andes Energía', 2],
    ['Delta Labs', 1],
  ]);
  assert.equal(companies[0].key, implementation().companyKey('Andes Energía'));
});

test('company search matches names and existing vacancy metadata signals', () => {
  const companies = implementation().deriveCompanies(vacancies);

  assert.deepEqual(implementation().searchCompanies(companies, 'energia').map(({ name }) => name), ['Andes Energía']);
  assert.deepEqual(implementation().searchCompanies(companies, 'GIS').map(({ name }) => name), ['Andes Energía']);
  assert.deepEqual(implementation().searchCompanies(companies, 'salta').map(({ name }) => name), ['Andes Energía']);
});

test('selecting a company filters the existing vacancies and clearing selection resets it', () => {
  const selected = implementation().filterVacancies(vacancies, implementation().companyKey('Andes Energía'));

  assert.deepEqual(selected.map(({ id }) => id), ['vacancy-1', 'vacancy-2']);
  assert.deepEqual(implementation().filterVacancies(vacancies, null), vacancies);
});

test('workspace defaults to Spanish-first work and excludes advanced-English requirements', () => {
  const englishRequired = {
    ...vacancies[2],
    id: 'vacancy-english-required',
    work_language: 'EN',
    listing_language: 'ES',
  };
  const candidates = [
    { ...vacancies[0], work_language: 'ES' },
    { ...vacancies[1], work_language: 'UNKNOWN', listing_language: 'ES' },
    englishRequired,
    { ...vacancies[3], company: 'Delta Labs', work_language: 'BILINGUAL' },
  ];
  const workspace = implementation().buildWorkspace(candidates);

  assert.equal(workspace.mode, 'Trabajo ahora · Español');
  assert.deepEqual(workspace.vacancies.map(({ id }) => id), ['vacancy-1', 'vacancy-2']);
  assert.deepEqual(workspace.companyIndex.map(({ name, vacancyCount }) => [name, vacancyCount]), [
    [vacancies[0].company, 2],
  ]);
});

test('Explorar todo includes all records and selection derives detail and linked vacancies', () => {
  const all = [...vacancies, {
    id: 'vacancy-english-required',
    company: 'Delta Labs',
    title: 'English-only role',
    work_language: 'EN',
    listing_language: 'ES',
    source_url: 'https://jobs.example.org/english',
  }];
  const selectedKey = implementation().companyKey('Delta Labs');
  const workspace = implementation().buildWorkspace(all, {
    mode: 'Explorar todo',
    selectedCompanyKey: selectedKey,
  });

  assert.equal(workspace.mode, 'Explorar todo');
  assert.equal(workspace.vacancies.length, all.length);
  assert.equal(workspace.selectedCompany.name, 'Delta Labs');
  assert.deepEqual(workspace.linkedVacancies.map(({ id }) => id), ['vacancy-3', 'vacancy-english-required']);
  assert.equal(implementation().officialSourceUrl(workspace.linkedVacancies[1]), 'https://jobs.example.org/english');
  assert.equal(workspace.linkedVacancies[1].location, undefined);
  assert.equal('applications' in workspace, false);
  assert.equal('crm' in workspace, false);
});

test('vacancies without verified coordinates report an honest no-map state', () => {
  const state = implementation().mapAvailability([
    ...vacancies,
    { coordinates_verified: true, latitude: null, longitude: null },
  ]);

  assert.equal(state.available, false);
  assert.equal(state.label, 'Sin coordenadas verificadas; no mostramos un mapa.');
});

test('map availability accepts only explicitly verified finite coordinates', () => {
  const mapAvailability = implementation().mapAvailability;

  assert.equal(mapAvailability([{ coordinates_verified: true, latitude: '', longitude: 0 }]).available, false);
  assert.deepEqual(mapAvailability([
    { coordinates_verified: true, latitude: -24.78, longitude: -65.41 },
  ]).points.map(({ latitude, longitude }) => [latitude, longitude]), [[-24.78, -65.41]]);
});

test('vacancy navigation uses only each public official HTTPS source URL', () => {
  assert.equal(implementation().officialSourceUrl(vacancies[0]), 'https://careers.example.com/jobs/1');
  assert.equal(implementation().officialSourceUrl({ source_url: 'javascript:alert(1)' }), null);
  assert.equal(implementation().officialSourceUrl({ url: 'https://unverified.example.com/job' }), null);
});

test('Vercel CSP permits the same-origin directory script without changing other directives', () => {
  const siteDirectory = new URL('../site/', import.meta.url);
  const html = readFileSync(new URL('index.html', siteDirectory), 'utf8');
  const config = JSON.parse(readFileSync(new URL('vercel.json', siteDirectory), 'utf8'));
  const csp = config.headers.flatMap(({ headers }) => headers)
    .find(({ key }) => key === 'Content-Security-Policy')?.value;

  assert.match(html, /<script src="\.\/company-directory\.js"><\/script>/);
  assert.equal(
    csp,
    "default-src 'none'; connect-src https://raw.githubusercontent.com; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'",
  );
});


test('Trabajo ahora excludes senior or explicitly incompatible vacancies regardless of listing Spanish', () => {
  const base = { ...vacancies[0], work_language: 'UNKNOWN', listing_language: 'ES' };
  const sample = [
    { ...base, id: 'junior', title: 'Analista GIS Junior', category: 'REVISAR' },
    { ...base, id: 'senior', title: 'Senior GIS Analyst', category: 'REVISAR' },
    { ...base, id: 'advanced', title: 'Python Developer', category: 'EXPLORAR' },
    { ...base, id: 'outside', title: 'Python Jr', argentina_eligible: 'NO' },
  ];
  assert.deepEqual(implementation().buildWorkspace(sample).vacancies.map(x => x.id), ['junior']);
  assert.equal(implementation().buildWorkspace(sample, {
    mode: 'Explorar todo'
  }).vacancies.length, 4);
});


test('Spanish-first priority gives GIS junior a higher rank than generic cloud seniority-unknown roles', () => {
  const base = { work_language: 'UNKNOWN', listing_language: 'ES', argentina_eligible: 'UNKNOWN' };
  const gisJunior = { ...base, company: 'Geo Córdoba', title: 'Analista GIS Junior', track: 'gis_geoscience' };
  const generic = { ...base, company: 'AWS Tech', title: 'Data Engineer GCP', track: 'software_ai', score: 100 };
  assert.ok(implementation().immediatePriority(gisJunior) > implementation().immediatePriority(generic));
  const workspace = implementation().buildWorkspace([generic, gisJunior]);
  assert.equal(workspace.companyIndex[0].name, 'Geo Córdoba');
  assert.equal(workspace.vacancies.length, 2);
});
