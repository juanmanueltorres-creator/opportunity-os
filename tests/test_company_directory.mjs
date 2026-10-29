import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
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
