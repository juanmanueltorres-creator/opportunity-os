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
  if (!vacancy || vacancy.category === 'EXPLORAR'
      || vacancy.work_language === 'EN' || vacancy.work_language === 'BILINGUAL'
      || vacancy.argentina_eligible === 'NO'
      || /\b(senior|sr\.?|staff|principal|director|head of)\b/i.test(String(vacancy.title || ''))) {
    return false;
  }

  return vacancy.work_language === 'ES'
    || (vacancy.work_language === 'UNKNOWN' && vacancy.listing_language === 'ES');
}

// Profile-first priority is deterministic and uses only public vacancy evidence.
// It is NOT a hiring/eligibility score or confirmation of a current opening.
function immediatePriority(vacancy) {
  const title = normalize(vacancy?.title ?? '');
  const track = normalize(vacancy?.track ?? '');
  let points = 0;
  if (/(?:\bgis\b|\bsig\b|geoespac|geospatial|geologia|geologo|mineri|cartograf|geomatic|teledeteccion|remote sensing|geoai)/.test(title + ' ' + track)) points += 45;
  if (/\b(junior|jr\.?|trainee|entry level|pasantia|joven profesional)\b/.test(title)) points += 26;
  if (/\b(python|fastapi|postgis|qgis|postgresql)\b/.test(title)) points += 24;
  if (/(?:soporte|support|backend|back.end|analista de datos|data analyst|data engineer|automatizacion|integrations)/.test(title)) points += 15;
  if (vacancy?.argentina_eligible === 'YES') points += 10;
  if (normalize(vacancy?.argentina_province) === 'cordoba') points += 10;
  if (vacancy?.work_language === 'ES') points += 10;
  else if (vacancy?.listing_language === 'ES') points += 2;
  return points;
}

function buildWorkspace(vacancies, options = {}) {
  const allVacancies = Array.isArray(vacancies) ? vacancies : [];
  const mode = options.mode === EXPLORE_ALL_MODE ? EXPLORE_ALL_MODE : WORK_NOW_MODE;
  const visibleVacancies = mode === EXPLORE_ALL_MODE
    ? allVacancies
    : allVacancies.filter(isSpanishFirstVacancy);
  const companyIndex = deriveCompanies(visibleVacancies);
  if (mode === WORK_NOW_MODE) companyIndex.sort((a, b) => (
    Math.max(...b.vacancies.map(immediatePriority))
    - Math.max(...a.vacancies.map(immediatePriority))
  ) || a.name.localeCompare(b.name, 'es'));
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
  immediatePriority,
  buildWorkspace,
  WORK_NOW_MODE,
  EXPLORE_ALL_MODE,
  mapAvailability,
  officialSourceUrl,
};

if (typeof module !== 'undefined' && module.exports) module.exports = companyDirectory;
if (typeof globalThis !== 'undefined') globalThis.CompanyDirectory = companyDirectory;
