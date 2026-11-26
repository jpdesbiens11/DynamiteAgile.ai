/* 0.60.130 (D-O-143): the « Filtre » of the competency grid only chooses which columns show -- « Grille du Space », « Tous »
   or one trade / technical group; it never posts to the server and it is kept per Space in this browser.
     node tests/js/competency_filter.js   (prints "competency_filter OK" or the failures) */
const fs = require("fs"), vm = require("vm"), path = require("path");

const el = (tag, attrs, ...kids) => ({ tag, attrs: attrs || {}, kids: kids.flat().filter(Boolean), value: "", listeners: {},
  addEventListener(type, fn) { this.listeners[type] = fn; } });
const store = {};
const posted = [];
const sandbox = { console, DA: { el, diamond: {}, api: { post: (u) => posted.push(u) } },
  localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = v; } } };
sandbox.window = sandbox; vm.createContext(sandbox);
const read = (f) => fs.readFileSync(path.join(__dirname, "..", "..", f), "utf8");
vm.runInContext(read("static/js/diamond/competency_profiles.js"), sandbox);
vm.runInContext(read("static/js/diamond/competency_grid.js").replace(/DA\.refreshIcons = [\s\S]*?\n  };\n/, ""), sandbox);
const D = sandbox.DA.diamond;
const failures = [];
const check = (name, ok, got) => { if (!ok) failures.push(name + " -> " + JSON.stringify(got)); };

const cat = ["MECH", "THERM", "PCB", "FW", "SYS", "PWR", "TEST", "OLD"].map((code) => ({ code, name: code, active: code !== "OLD" }));
const comp = { catalog: cat, columns: ["MECH", "PCB", "FW", "PWR", "TEST", "OLD"],
  lines: [{ ratings: { MECH: 3, OLD: 2 } }, { ratings: { FW: 5 } }],
  profiles: [{ key: "software", name: "Logiciel embarqué", codes: ["FW", "SYS", "PCB", "TEST"] }] };
const codes = (filter) => D.competencyColumns(comp, filter).map((c) => c.code).join(",");

check("grid", codes("") === "MECH,PCB,FW,PWR,TEST,OLD", codes(""));
check("all: every active one and any rated one", codes("all") === "MECH,THERM,PCB,FW,SYS,PWR,TEST,OLD", codes("all"));
check("profile", codes("software") === "FW,SYS,PCB,TEST", codes("software"));
check("unknown filter = grid", codes("nope") === codes(""), codes("nope"));
check("ratings untouched", comp.lines[0].ratings.MECH === 3 && comp.lines[0].ratings.OLD === 2, comp.lines[0].ratings);

const ctx = { pid: 7 };
check("default", D.competencyFilter(ctx) === "", D.competencyFilter(ctx));
let changed = null;
const label = D.profilePicker(ctx, comp, (v) => { changed = v; });
const pick = label.kids.find((k) => k.tag === "select");
check("options", pick.kids.map((o) => o.attrs.value).join("|") === "|all|software", pick.kids.map((o) => o.attrs.value));
check("option names", pick.kids[1].kids[0] === "Tous" && pick.kids[0].kids[0] === "Grille du Space", pick.kids.map((o) => o.kids[0]));
pick.value = "all"; pick.listeners.change();
check("kept per Space", D.competencyFilter(ctx) === "all" && D.competencyFilter({ pid: 8 }) === "", store);
check("redraw called", changed === "all", changed);
check("nothing posted", posted.length === 0, posted);

console.log(failures.length ? "competency_filter FAILED\n" + failures.join("\n") : "competency_filter OK");
process.exit(failures.length ? 1 : 0);
