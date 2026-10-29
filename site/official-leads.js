"use strict";

// Human-reviewed employer/job-board listings, NOT proof of open applications.
// Source URLs are direct public vacancy pages; page age and eligibility require checks.
// The featured list contains no applicant correspondence or personal status.
const OFFICIAL_LEADS = Object.freeze([
  {
    id: "bellone-fullstack-jr-cordoba",
    company: "Julio Bellone y Asociados",
    title: "Desarrollador Full Stack Junior (presencial)",
    source_url: "https://ar.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-desarrollador-full-stack-junior-presencial-en-cordoba-365abf4a3ceaf48861373e686dcf3405",
    location: "Córdoba Capital, Argentina",
    modality: "Presencial, jornada completa",
    reviewed_at: "2026-10-29",
    deadline: null,
    requirements: "React, JavaScript, Node.js/Express, APIs REST, PostgreSQL/MySQL, Git. Computrabajo informa dos años de experiencia y educación terciaria.",
    check: "Verificar que el botón Postularme siga habilitado. Node/Express es requisito del aviso: no confundir con experiencia práctica en FastAPI. Confirmar experiencia exigida y salario.",
    priority: 1
  },
  {
    id: "campy-fullstack-mining-jr",
    company: "Campy / Upgrade Stack Company",
    title: "Full Stack Developer Junior — software para campamentos mineros",
    source_url: "https://ar.linkedin.com/jobs/view/programador-full-stack-at-campy-4478232678",
    location: "Salta Capital, Argentina",
    modality: "Presencial, jornada completa",
    reviewed_at: "2026-10-29",
    deadline: null,
    requirements: "Desarrollo full stack junior de funcionalidades de plataforma para campamentos mineros, APIs, bases de datos y herramientas web. Ver aviso para tecnologías exigidas.",
    check: "Exige trabajar presencialmente en Salta Capital. Confirmar reubicación y que la oferta continúe admitiendo postulaciones.",
    priority: 3
  },
  {
    id: "erm-r00032104",
    company: "ERM",
    title: "Geólogo/a Junior — consultoría ambiental (SI&R)",
    source_url: "https://erm.wd3.myworkdayjobs.com/ERM_EarlyCareers/job/Buenos-Aires-Argentina/Geologist-Consulting-Associate-SI-R--Entry-Level-_R00032104-1",
    location: "Buenos Aires, Argentina",
    modality: "No indicada; trabajo de campo y viajes",
    reviewed_at: "2026-10-29",
    deadline: "2026-10-31",
    requirements: "Geología o carrera afín (estudiantes avanzados admitidos). Hidrogeología básica, inglés intermedio o en desarrollo, licencia de conducir vigente, campo y viajes. GIS valorado.",
    check: "Requiere disponibilidad para Buenos Aires, viajes y licencia de conducir. Confirmar aceptación de formación afín y vigencia antes de aplicar.",
    priority: 2
  },
  {
    id: "aeroterra-analista-funcional-gis",
    company: "Aeroterra",
    title: "Analista Funcional GIS",
    source_url: "https://www.aeroterra.com/es-ar/trabaja-con-nosotros/busquedas-actuales/analista-funcional-gis",
    location: "CABA — Catalinas, Retiro",
    modality: "Oficina en CABA; no se anuncia remoto",
    reviewed_at: "2026-10-29",
    deadline: null,
    requirements: "Graduado o próximo a recibirse en Sistemas. Relevamiento funcional, ArcGIS, SQL; Python, JavaScript, Node.js y metodologías ágiles.",
    check: "Se exige formación en Sistemas. Comprobar si aceptan formación en geociencias y experiencia de software antes de postular.",
    priority: 2
  },
]);

function officialLeadsForDate(now = new Date()) {
  const date = now instanceof Date ? now : new Date(now);
  if (!Number.isFinite(date.valueOf())) return [];
  return OFFICIAL_LEADS.filter((job) => {
    const expiry = job.deadline
      ? new Date(job.deadline + "T23:59:59-03:00")
      : new Date(job.reviewed_at + "T00:00:00-03:00").valueOf() + 14 * 86400000;
    if (date.valueOf() > Number(expiry)) return false;
    try {
      const u = new URL(job.source_url);
      return u.protocol === "https:" && !u.username && !u.password;
    } catch {
      return false;
    }
  }).sort((a, b) => a.priority - b.priority);
}

const officialLeads = { OFFICIAL_LEADS, officialLeadsForDate };
if (typeof module !== "undefined" && module.exports) module.exports = officialLeads;
if (typeof window !== "undefined") window.OfficialLeads = officialLeads;
