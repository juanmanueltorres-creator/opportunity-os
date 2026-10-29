"use strict";
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const sandbox = { module: { exports: {} }, URL };
vm.runInNewContext(fs.readFileSync(new URL("../site/cv-workspace.js", import.meta.url), "utf8"), sandbox);
const cv = sandbox.module.exports;

test("sanitizes candidate input and does not fabricate background",()=>{
 const p=cv.sanitize({name:"  Persona  ",summary:"Estudios verificados",fake:"No"});
 assert.equal(p.name,"Persona");
 assert.equal(p.summary,"Estudios verificados");
 assert.equal(Object.hasOwn(p,"fake"),false);
 assert.equal(p.experience,"");
});

test("reorders only stated skills, never invents from requirements",()=>{
 const p={skills:"QGIS, Python, Blender, PostGIS"};
 const list=cv.skillsForJob(p,{title:"GIS Analyst",description:"Python and PostGIS required"});
 assert.deepEqual([...list.slice(0,2)],["Python","PostGIS"]);
 assert.equal(list.includes("Node.js"),false);
 assert.equal(list.length,4);
});

test("does not trust arbitrary links",()=>{
 assert.equal(cv.safeHttp("javascript:alert(1)"),null);
 assert.equal(cv.safeHttp("http://example.com"),null);
 assert.equal(cv.safeHttp("https://user:pass@example.com"),null);
 assert.equal(cv.safeHttp("https://example.com/cv"),"https://example.com/cv");
});

test("new workspace is an explicit print-only, in-browser CV operation",()=>{
 const html=fs.readFileSync(new URL("../site/index.html", import.meta.url),"utf8");
 const code=fs.readFileSync(new URL("../site/cv-workspace.js", import.meta.url),"utf8");
 assert.ok(html.includes("window.CvWorkspace.open(j)"));
 assert.ok(html.includes("window.CvWorkspace.open({"));
 assert.ok(html.includes('src="./cv-workspace.js"'));
 assert.ok(html.includes("@media print"));
 assert.ok(code.includes('root.print()'));
 assert.ok(code.includes("Guardar perfil aquí"));
 assert.ok(code.includes("Borrar perfil guardado"));
 assert.ok(!code.includes("fetch("));
 assert.ok(!code.includes("XMLHttpRequest"));
 assert.ok(!code.includes("eval("));
 assert.ok(!code.includes("innerHTML"));
 assert.ok(!code.includes("GEMINI_API_KEY"));
});
