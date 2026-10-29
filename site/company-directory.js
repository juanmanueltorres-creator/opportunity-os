'use strict';

const normalize = (value) => String(value ?? '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .toLowerCase()
  .trim()
  .replace(/\s+/g, ' ');

function companyKey(name) {
  return normalize(name);
}

function deriveCompanies(vacancies) {
  const companies = new Map();

  for (const vacancy of Array.isArray(vacancies) ? vacancies : []) {
    const name = String(vacancy?.company ?? '').trim();
    const key = companyKey(name);
    if (!key) continue;

    if (!companies.has(key)) companies.set(key, { key, name, vacancies: [] });
    companies.get(key).vacancies.push(vacancy);
  }

  return [...companies.values()].map((company) => ({
    ...company,
    vacancyCount: company.vacancies.length,
  }));
}

function searchCompanies(companies, query) {
  const needle = normalize(query);
  if (!needle) return Array.isArray(companies) ? companies : [];

  return (Array.isArray(companies) ? companies : []).filter((company) => {
    const evidence = [company.name];
    for (const vacancy of company.vacancies ?? []) {
      evidence.push(
        vacancy.title,
        vacancy.track,
        vacancy.company_industry,
        vacancy.location,
        ...(Array.isArray(vacancy.topics) ? vacancy.topics : []),
      );
    }
    return normalize(evidence.filter(Boolean).join(' ')).includes(needle);
  });
}

function filterVacancies(vacancies, selectedCompanyKey) {
  if (!selectedCompanyKey) return Array.isArray(vacancies) ? vacancies : [];
  return (Array.isArray(vacancies) ? vacancies : []).filter(
    (vacancy) => companyKey(vacancy?.company) === selectedCompanyKey,
  );
}

const WORK_NOW_MODE = 'Trabajo ahora · Español';
const EXPLORE_ALL_MODE = 'Explorar todo';

function isSpanishFirstVacancy(vacancy) {
  if (!vacancy || vacancy.work_language === 'EN' || vacancy.work_language === 'BILINGUAL') {
    return false;
  }

  return vacancy.work_language === 'ES'
    || (vacancy.work_language === 'UNKNOWN' && vacancy.listing_language === 'ES');
}

function buildWorkspace(vacancies, options = {}) {
  const allVacancies = Array.isArray(vacancies) ? vacancies : [];
  const mode = options.mode === EXPLORE_ALL_MODE ? EXPLORE_ALL_MODE : WORK_NOW_MODE;
  const visibleVacancies = mode === EXPLORE_ALL_MODE
    ? allVacancies
    : allVacancies.filter(isSpanishFirstVacancy);
  const companyIndex = deriveCompanies(visibleVacancies);
  const selectedCompanyKey = options.selectedCompanyKey || null;
  const selectedCompany = companyIndex.find(({ key }) => key === selectedCompanyKey) || null;
  const linkedVacancies = selectedCompany ? selectedCompany.vacancies : [];

  return {
    mode,
    vacancies: visibleVacancies,
    companyIndex,
    selectedCompany,
    linkedVacancies,
  };
}

function mapAvailability(vacancies) {
  const hasCoordinate = (value) =>
    (typeof value === 'number' || (typeof value === 'string' && value.trim() !== ''))
    && Number.isFinite(Number(value));
  const points = (Array.isArray(vacancies) ? vacancies : []).filter((vacancy) =>
    vacancy?.coordinates_verified === true
    && hasCoordinate(vacancy.latitude)
    && hasCoordinate(vacancy.longitude),
  );

  return points.length
    ? { available: true, points, label: `${points.length} ubicaciones con coordenadas verificadas.` }
    : { available: false, points: [], label: 'Sin coordenadas verificadas; no mostramos un mapa.' };
}

function officialSourceUrl(vacancy) {
  try {
    const url = new URL(vacancy?.source_url);
    return url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
}

const companyDirectory = {
  companyKey,
  deriveCompanies,
  searchCompanies,
  filterVacancies,
  isSpanishFirstVacancy,
  buildWorkspace,
  WORK_NOW_MODE,
  EXPLORE_ALL_MODE,
  mapAvailability,
  officialSourceUrl,
};

if (typeof module !== 'undefined' && module.exports) module.exports = companyDirectory;
if (typeof globalThis !== 'undefined') globalThis.CompanyDirectory = companyDirectory;
