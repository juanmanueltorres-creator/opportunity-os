/* Opportunity OS — private, browser-only resume worksheet.
   No request to Gemini, Supabase, GitHub or the source job board is made.
   Browser Print lets a human review and Save as PDF without exposing CV data. */
(function(root) {
"use strict";
const STORAGE = "opportunity-os-owner-cv-v1";
const FIELDS = Object.freeze([
  ["name","Nombre y apellido","text"],
  ["headline","Perfil profesional","text"],
  ["city","Ciudad / ubicación","text"],
  ["email","Correo electrónico","email"],
  ["phone","Teléfono (opcional)","text"],
  ["links","Enlaces públicos (uno por línea; https://)","textarea"],
  ["summary","Resumen profesional (solo hechos comprobables)","textarea"],
  ["skills","Herramientas y habilidades reales (separadas por coma o línea)","textarea"],
  ["experience","Experiencia laboral (una responsabilidad o logro comprobable por línea)","textarea"],
  ["education","Formación académica (una por línea)","textarea"],
  ["projects","Proyectos demostrables (uno por línea, con enlace cuando exista)","textarea"],
]);
const IDMAX = {name:140,headline:180,city:150,email:200,phone:80,
               links:1400,summary:1600,skills:1200,experience:4000,
               education:1800,projects:3000};
const clean = (text, max=2000) => String(text == null?"":text).trim().slice(0,max);
const lines = (text,limit=30) => clean(text,4000).split(/\r?\n/).map(v=>v.trim()).filter(Boolean).slice(0,limit);
const normalized = text=>clean(text).normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase();
function safeHttp(url){
  try{const x = new URL(url);return x.protocol==="https:" && !x.username && !x.password && !x.port ? x.href : null;}catch{return null;}
}
function sanitize(input){
 const result={};
 for(const [key] of FIELDS)result[key]=clean(input && input[key],IDMAX[key]);
 return result;
}
function skillsForJob(profile,job){
 const all = clean(profile.skills,1200).split(/[,\n;]+/).map(v=>v.trim()).filter(Boolean).slice(0,60);
 const info = normalized([job.title,job.description,job.requirements].filter(Boolean).join(" ")).slice(0,6000);
 const scored = all.map((value,index)=>{
   const norm=normalized(value);
   // Only annotate a skill already asserted by the candidate, never invent one.
   const match = norm.length>=2 && info.includes(norm);
   return {value,index,match};
 });
 scored.sort((a,b)=>Number(b.match)-Number(a.match)||a.index-b.index);
 return scored.map(x=>x.value);
}
function makeEl(tag,text,cls){
 const node=document.createElement(tag);
 if(text!==undefined&&text!==null)node.textContent=String(text);
 if(cls)node.className=cls;
 return node;
}
function createPrintable(profile,job){
 const p=sanitize(profile);
 if(!p.name||!p.summary)throw new Error("Completá al menos nombre y resumen profesional antes de imprimir.");
 const section=makeEl("section",null,"cv-sheet");
 section.setAttribute("aria-label","CV preparado para impresión");
 section.append(makeEl("h1",p.name));
 if(p.headline)section.append(makeEl("h2",p.headline));
 const contact=[p.city,p.email,p.phone].filter(Boolean).join(" · ");
 if(contact)section.append(makeEl("p",contact,"cv-contact"));
 const urls=makeEl("p",null,"cv-links");
 for(const item of lines(p.links,12)){
   const href=safeHttp(item);
   if(!href)continue;
   const a=makeEl("a",item);a.href=href;a.rel="noopener noreferrer";a.target="_blank";
   urls.append(a,document.createTextNode("   "));
 }
 if(urls.childNodes.length)section.append(urls);
 function part(label,values){
   const list=Array.isArray(values)?values:lines(values,28);
   if(!list.length)return;
   section.append(makeEl("h3",label));
   const u=makeEl("ul");
   for(const v of list)u.append(makeEl("li",v));
   section.append(u);
 }
 section.append(makeEl("h3","Perfil"));
 section.append(makeEl("p",p.summary));
 part("Tecnologías y conocimientos",skillsForJob(p,job));
 part("Experiencia",p.experience);
 part("Proyectos",p.projects);
 part("Formación",p.education);
 return section;
}
function createApp(){
 const modal=makeEl("dialog",null,"cv-dialog");
 modal.id="cvComposer";
 modal.setAttribute("aria-labelledby","cvComposerTitle");
 const heading=makeEl("h2","Preparar CV para esta vacante");heading.id="cvComposerTitle";modal.append(heading);
 const jobLabel=makeEl("p",null,"note");jobLabel.id="cvJobLabel";modal.append(jobLabel);
 modal.append(makeEl("p","No se inventa experiencia ni se envían datos. Revisá cada campo. Tu perfil solo se guarda en este navegador si pulsás «Guardar perfil aquí». La exportación usa Imprimir → Guardar como PDF.","note"));
 const jobDetails=makeEl("details");jobDetails.append(makeEl("summary","Requisitos de la vacante"));
 const jDetailsText=makeEl("p",null,"note");jobDetails.append(jDetailsText);modal.append(jobDetails);
 const grid=makeEl("div",null,"cv-field-grid");
 const inputs={};
 for(const [key,label,type] of FIELDS){
   const field=makeEl("label",null,"cv-field");
   field.append(makeEl("span",label));
   const input=makeEl(type==="textarea"?"textarea":"input");
   input.id="cvField_"+key;
   input.maxLength=IDMAX[key];
   if(type!=="textarea")input.type=type;
   if(type==="textarea")input.rows=["experience","projects"].includes(key)?4:2;
   field.append(input);
   inputs[key]=input;grid.append(field);
 }
 modal.append(grid);
 const actions=makeEl("div",null,"cv-actions");
 function btn(text,fn){const button=makeEl("button",text,"smallbtn");button.type="button";button.addEventListener("click",fn);actions.append(button);return button;}
 const message=makeEl("p",null,"note");message.setAttribute("role","status");
 const source=makeEl("a","Abrir aviso original");source.target="_blank";source.rel="noopener noreferrer";actions.append(source);
 let job={};
 function read(){return sanitize(Object.fromEntries(FIELDS.map(([key])=>[key,inputs[key].value])));}
 function write(v){const p=sanitize(v);for(const [key] of FIELDS)inputs[key].value=p[key];}
 function saved(){
   try{
     const raw=root.localStorage.getItem(STORAGE);
     if(raw&&raw.length<=16000)return sanitize(JSON.parse(raw));
   }catch{}
   return sanitize({});
 }
 btn("Guardar perfil aquí",()=>{
   try{root.localStorage.setItem(STORAGE,JSON.stringify(read()));message.textContent="Perfil guardado solo en este navegador.";}
   catch{message.textContent="No se pudo guardar en este navegador. Podés imprimir sin guardar.";}
 });
 btn("Borrar perfil guardado",()=>{
   try{root.localStorage.removeItem(STORAGE);}catch{}
   message.textContent="Se borró la copia guardada. Los campos siguen abiertos para revisar.";
 });
 btn("Guardar PDF (Imprimir)",()=>{
   try{
     const printed=createPrintable(read(),job);
     const box=document.getElementById("cvPrintable");
     box.replaceChildren(printed);
     message.textContent="En el diálogo de impresión elegí «Guardar como PDF». Revisá la vista previa y los enlaces.";
     root.print();
   }catch(e){message.textContent=e.message||"No se pudo preparar el CV.";}
 });
 btn("Cerrar",()=>modal.close());
 modal.append(actions,message);
 const print=makeEl("div");print.id="cvPrintable";print.setAttribute("aria-hidden","true");
 document.body.append(modal,print);
 function open(vacancy){
   job=vacancy||{};
   jobLabel.textContent=(job.company||"Empresa no informada")+" · "+(job.title||"Puesto sin título");
   jDetailsText.textContent=clean(job.description||job.requirements||"Requisitos no disponibles en esta captura; consultá la fuente original.",6000);
   const url=safeHttp(job.source_url);source.hidden=!url;if(url)source.href=url;
   write(saved());
   message.textContent="";
   modal.showModal();
 }
 return {open,profile:read};
}
const exported={sanitize,skillsForJob,safeHttp,createPrintable};
if(typeof module==="object"&&module.exports)module.exports=exported;
if(root&&root.document){
 function boot(){root.CvWorkspace=Object.assign(createApp(),exported);}
 if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot,{once:true});
 else boot();
}
})(typeof window!=="undefined"?window:undefined);
