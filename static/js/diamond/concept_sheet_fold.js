/* Diamond · « Feuilles de concept » by branch (0.60.128, D-O-141): when the sheets pile up, the page reads like the tree -- one
   foldable block per branch (the secondary function above the brick's functions), one foldable block per brick inside it, the
   sheets as cards (0.60.132, D-O-145: the AI of a branch is chosen in « ↔ IA : feuilles de concept », concept_round.js). « Tout ouvrir / Tout fermer » at the top; what is open is remembered in
   this browser for the Space (a convenience: nothing is written on the server). Closed by default past 12 sheets. */
(function () {
  "use strict";

  const { el } = DA;
  const A = DA.agile;
  const D = DA.diamond;
  const MANY = 12;

  const storeKey = (ctx) => "dm-csheets-open-" + ctx.key;
  function remembered(ctx) {
    try { return JSON.parse(localStorage.getItem(storeKey(ctx)) || "null"); } catch (err) { return null; }
  }
  function remember(ctx, holder) {
    const open = [...holder.querySelectorAll("details[data-fold]")].filter((d) => d.open).map((d) => d.dataset.fold);
    try { localStorage.setItem(storeKey(ctx), JSON.stringify(open)); } catch (err) { /* private window: not kept */ }
  }

  /* [{branch: function | null, bricks: [{concept, sheets}]}] in the order of the tree */
  function branches(cdata, sheets) {
    const fns = new Map(cdata.functions.map((f) => [f.id, f]));
    const branchOf = (c) => {
      let cur = c.function_ids.map((id) => fns.get(id)).find(Boolean);
      while (cur && cur.level > 2 && fns.get(cur.parent_id)) cur = fns.get(cur.parent_id);
      return cur && cur.level === 2 ? cur : null;
    };
    const order = new Map(cdata.functions.map((f, i) => [f.id, i]));
    const out = new Map();
    cdata.concepts.forEach((c) => {
      const mine = sheets.filter((s) => s.concept_id === c.id);
      if (!mine.length) return;
      const b = branchOf(c);
      const key = b ? b.id : 0;
      if (!out.has(key)) out.set(key, { branch: b, bricks: [] });
      out.get(key).bricks.push({ concept: c, sheets: mine });
    });
    return [...out.values()].sort((x, y) => (x.branch ? order.get(x.branch.id) : 1e9) - (y.branch ? order.get(y.branch.id) : 1e9));
  }

  function fold(id, isOpen, summary, body, onToggle) {
    const box = el("details", { class: "dm-fold", "data-fold": id }, el("summary", null, summary), body);
    box.open = isOpen;
    box.addEventListener("toggle", onToggle);
    return box;
  }

  /* card(s): the card of one sheet (concept_sheets.js); reload: redraw after a change */
  function view(ctx, data, cdata, card, editable, reload) {
    const holder = el("div", { class: "dm-folds", "data-new": "0.60.128-sheets-fold" });
    const kept = remembered(ctx);
    const closed = data.sheets.length > MANY;
    const isOpen = (id) => (kept ? kept.includes(id) : !closed);
    const save = () => remember(ctx, holder);
    const groups = branches(cdata, data.sheets);
    const setAll = (open) => { holder.querySelectorAll("details[data-fold]").forEach((d) => { d.open = open; }); save(); };
    holder.append(el("div", { class: "dm-actions dm-fold-tools" },
      el("span", { class: "muted" }, groups.length + " branche(s) · " + data.sheets.length + " feuille(s)"),
      el("button", { type: "button", class: "btn btn-small", onclick: () => setAll(true) }, "Tout ouvrir"),
      el("button", { type: "button", class: "btn btn-small", onclick: () => setAll(false) }, "Tout fermer")));
    groups.forEach((g) => {
      const bid = "b" + (g.branch ? g.branch.id : 0);
      const count = g.bricks.reduce((n, b) => n + b.sheets.length, 0);
      const bricks = g.bricks.map(({ concept: c, sheets }) => fold("c" + c.id, isOpen("c" + c.id),
        [el("a", { class: "dm-code", href: A.href(ctx, "concepts/" + c.code), onclick: (ev) => ev.stopPropagation() }, c.code),
          " " + (c.initial_name ? "« " + c.initial_name + " » " : "") + c.name,
          el("span", { class: "muted" }, " · " + sheets.length + " feuille" + (sheets.length > 1 ? "s" : "")),
          c.frozen ? el("span", { class: "badge badge-ok" }, "Figée") : null],
        el("div", { class: "dm-sheets" }, sheets.map((s) => card(s))), save));
      holder.append(fold(bid, isOpen(bid),
        [el("strong", null, g.branch ? "F" + g.branch.number + " " + g.branch.text : "Briques sans fonction de l'arbre"),
          el("span", { class: "muted" }, " · " + g.bricks.length + " brique(s) · " + count + " feuille(s)"),
          g.branch ? el("button", { type: "button", class: "btn btn-small dm-fold-review", "data-new": "0.60.133-review-branch",
            "data-tip": "Revoir les feuilles de cette branche, une à la fois",
            onclick: (ev) => { ev.preventDefault(); ev.stopPropagation(); D.openReview(ctx, reload, { scope: "f" + g.branch.id }); } }, "▶ Revue") : null],
        el("div", { class: "dm-fold-body" }, bricks), save));
    });
    return holder;
  }

  D.sheetsByBranch = view;
  D.sheetBranches = branches;  // 0.60.133 (D-O-146): the order of the tree, for « Revue »
})();
