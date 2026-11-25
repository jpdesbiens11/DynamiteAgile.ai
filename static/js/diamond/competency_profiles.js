/* Diamond · the filter of the competencies (0.60.130, D-O-143; it was the « Profil de grille » of 0.60.119, which replaced the columns
   and erased ratings). A view only: « Colonnes du Space » (the ones the team chose), « Toutes / All » (the whole catalogue at
   once), or the group of one kind of product (mechatronics, electronics and power, embedded software…). Nothing is written: the
   choice stays in this browser, per Space, and is shared by the tree and « Compétences et équipe ». */
(function () {
  "use strict";

  const { el } = DA;
  const D = DA.diamond;
  const SPACE = "space", ALL = "all";
  const memory = {};  // when the browser keeps nothing (private window)
  const storeKey = (ctx) => "dm-comp-filter-" + ctx.pid;

  /* the choice of this viewer; an unknown one (a group that left) is the columns of the Space */
  function filter(ctx, comp) {
    let key = memory[ctx.pid];
    try { key = key || localStorage.getItem(storeKey(ctx)); } catch (err) { /* private window */ }
    return key && (key === ALL || groups(comp).some((p) => p.key === key)) ? key : SPACE;
  }

  const groups = (comp) => (comp.profiles || []).filter((p) => p.codes.length);

  /* the columns a filter shows, as competencies of the catalogue */
  function filtered(comp, key) {
    if (key === ALL) {  // the catalogue in its order, plus a deactivated one the Space still uses
      const used = new Set(comp.columns);
      return comp.catalog.filter((c) => c.active || used.has(c.code));
    }
    const group = groups(comp).find((p) => p.key === key);
    if (!group) return D.competencyColumns(comp);
    const byCode = new Map(comp.catalog.map((c) => [c.code, c]));
    return group.codes.map((code) => byCode.get(code)).filter(Boolean);
  }

  /* the select; onChange redraws the page */
  function filterPicker(ctx, comp, onChange) {
    const key = filter(ctx, comp);
    const option = (value, label) => el("option", { value, selected: value === key ? "selected" : null }, label);
    const pick = el("select", { class: "dm-cg-profile", "aria-label": "Compétences affichées", "data-new": "0.60.130-competency-filter",
      "data-tip": "Filtre d'affichage : aucune colonne ni note n'est changée" },
    option(SPACE, "Compétences : colonnes du Space"), option(ALL, "Compétences : toutes / All"),
    groups(comp).map((p) => option(p.key, p.name + " — " + p.codes.join(", "))));
    pick.addEventListener("change", () => {
      memory[ctx.pid] = pick.value;
      try { localStorage.setItem(storeKey(ctx), pick.value); } catch (err) { /* private window: this visit only */ }
      onChange(pick.value);
    });
    return pick;
  }

  Object.assign(D, { competencyFilter: filter, competencyFiltered: filtered, competencyFilterPicker: filterPicker });
})();
