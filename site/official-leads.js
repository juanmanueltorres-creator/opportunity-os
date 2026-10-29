"use strict";

// Human-reviewed public employer / university postings, NOT proof of availability.
// All entries include an official primary-source URL and date reviewed.
// Neither the company nor the location may be inferred from a job aggregator.
const OFFICIAL_LEADS = Object.freeze([
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
    priority: 1
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
