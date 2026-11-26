/* Diamond · filter of the competency grid (0.60.130, D-O-143; was « Profil de grille ▾ », 0.60.119, D-O-132). Under the tree and at
   the top of « Compétences et équipe », a list chooses which competency columns show: « Grille du Space » (the columns the team
   chose, with « + » and « Retirer de la grille »), « Tous » (every active competency of the catalogue, and any one a line rates),
   or one trade / technical group (mechatronics, electronics and power, embedded software…). A filter only shows: no rating is
   erased, nothing is sent to the server; the choice is kept per Space in this browser. */
(function () {
  "use strict";

  const { el } = DA;
  const D = DA.diamond;
  const KEY = "diamond.competency.filter.";
  const GRID = "", ALL = "all";

  function getFilter(ctx) {
    try { return localStorage.getItem(KEY + ctx.pid) || GRID; } catch (err) { return GRID; }
  }

  function setFilter(ctx, value) {
    try { localStorage.setItem(KEY + ctx.pid, value || GRID); } catch (err) { /* private window: not kept */ }
  }

  /* the codes a filter shows, in order; null for the grid of the Space (competency_grid.js reads comp.columns) */
  function filterCodes(comp, filter) {
    if (!filter) return null;
    const active = comp.catalog.filter((c) => c.active).map((c) => c.code);
    if (filter === ALL) {
      const rated = new Set(comp.lines.flatMap((ln) => Object.keys(ln.ratings)));
      return comp.catalog.filter((c) => c.active || rated.has(c.code)).map((c) => c.code);
    }
    const p = (comp.profiles || []).find((x) => x.key === filter);
    return p ? p.codes.filter((c) => active.includes(c)) : null;
  }

  /* comp: the payload of /competencies; onChange(value): redraws with the new filter (already kept) */
  function profilePicker(ctx, comp, onChange) {
    const value = getFilter(ctx);
    const pick = el("select", { class: "dm-cg-profile", "aria-label": "Filtrer les compétences", "data-new": "0.60.130-competency-filter",
      "data-tip": "Afficher seulement les compétences d'un métier ou d'un groupe technique (aucune note n'est effacée)" },
    el("option", { value: GRID }, "Grille du Space"),
    el("option", { value: ALL }, "Tous"),
    (comp.profiles || []).filter((p) => p.codes.length).map((p) => el("option", { value: p.key }, p.name)));
    pick.value = (comp.profiles || []).some((p) => p.key === value) || value === ALL ? value : GRID;
    pick.addEventListener("change", () => { setFilter(ctx, pick.value); onChange(pick.value); });
    return el("label", { class: "dm-cg-filter" }, el("span", { class: "muted" }, "Filtre :"), pick);
  }

  Object.assign(D, { profilePicker, competencyFilter: getFilter, competencyFilterCodes: filterCodes });
})();
