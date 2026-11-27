/* Diamond · « Revue » of the concept sheets (0.60.133, D-O-146): one sheet at a time, full screen, in the order of the tree
   (branch, brick, number: CB-6.9 before CB-6.10); « Suivant » on the last sheet of a branch goes on to the next branch.
   Scope: every branch, one branch or one brick; filter: all, to review (Open and not seen), dropped.
   ← / → previous / next · G keep (seen) · E drop (« Dropped », seen) · Suppr delete (gone at once, « Annuler » for 5 s: the
   server is called only after) · M edit · Échap close. Seen is shared by the team (concept_review.py); the place in the review
   is remembered in this browser for the Space. A frozen brick is read only; a sheet retained by a Pugh matrix cannot be deleted. */
(function () {
  "use strict";

  const { api, el, clear, toast } = DA;
  const D = DA.diamond;
  const A = DA.agile;
  const UNDO_MS = 5000;
  const store = (ctx) => "dm-review-" + ctx.key;

  function remembered(ctx) {
    try { return JSON.parse(localStorage.getItem(store(ctx)) || "{}"); } catch (err) { return {}; }
  }
  function remember(ctx, state) {
    try { localStorage.setItem(store(ctx), JSON.stringify(state)); } catch (err) { /* private window: not kept */ }
  }

  /* Every sheet in the order of the tree, with its branch and its brick */
  function ordered(data, cdata) {
    const out = [];
    D.sheetBranches(cdata, data.sheets).forEach((g) => g.bricks.forEach((b) => b.sheets.forEach((s) =>
      out.push({ sheet: s, branch: g.branch, concept: b.concept }))));
    return out;
  }

  const seen = (s) => Boolean(s.reviewed_at);
  const FILTERS = { all: () => true, todo: (s) => s.status === "open" && !seen(s), dropped: (s) => s.status === "dropped" };

  async function open(ctx, done, start) {
    const [data, cdata] = await Promise.all([api.get(D.base(ctx) + "/sheets"), api.get(D.base(ctx) + "/concepts")]);
    let all = ordered(data, cdata);
    if (!all.length) { toast("Aucune feuille de concept à revoir.", "info"); return; }
    const editable = A.canEdit(ctx);
    const kept = remembered(ctx);
    const state = { scope: (start && start.scope) || kept.scope || "all", filter: kept.filter || "all", id: (start && start.id) || kept.id };
    const pending = new Map();  // sheet id -> { timer, item, index }
    let changed = false;

    const branches = [];
    all.forEach((it) => { if (it.branch && !branches.some((b) => b.id === it.branch.id)) branches.push(it.branch); });
    const scopeSel = el("select", { "aria-label": "Portée de la revue" }, el("option", { value: "all" }, "Toutes les branches"),
      branches.map((b) => el("option", { value: "f" + b.id }, "F" + b.number + " " + b.text)),
      [...new Map(all.map((it) => [it.concept.id, it.concept])).values()].map((c) =>
        el("option", { value: "c" + c.id }, "  " + c.code + " " + (c.initial_name || c.name))));
    const filterSel = el("select", { "aria-label": "Filtre" }, el("option", { value: "all" }, "Toutes"),
      el("option", { value: "todo" }, "À revoir"), el("option", { value: "dropped" }, "Écartées"));
    scopeSel.value = state.scope;
    if (scopeSel.value !== state.scope) scopeSel.value = state.scope = "all";
    filterSel.value = state.filter;

    const inScope = () => all.filter((it) => !pending.has(it.sheet.id) && (state.scope === "all"
      || (state.scope[0] === "f" && it.branch && "f" + it.branch.id === state.scope)
      || (state.scope[0] === "c" && "c" + it.concept.id === state.scope)));
    const list = () => inScope().filter((it) => FILTERS[state.filter](it.sheet));

    const counter = el("span", { class: "dm-review-count", role: "status" });
    const stage = el("div", { class: "dm-review-stage" });
    const side = el("div", { class: "dm-review-side" });
    const undoBar = el("div", { class: "dm-review-undo", hidden: true });
    const root = el("div", { class: "dm-review", role: "dialog", "aria-modal": "true", "aria-label": "Revue des feuilles de concept",
      "data-new": "0.60.133-review" });

    const flush = async () => {  // the deletions still waiting, sent now (closing the review)
      const ids = [...pending.keys()];
      ids.forEach((id) => clearTimeout(pending.get(id).timer));
      await Promise.all(ids.map((id) => send(id)));
    };
    const send = async (id) => {
      const p = pending.get(id);
      if (!p) return;
      pending.delete(id);
      try {
        await api.del(D.base(ctx) + "/sheets/" + id);
        all = all.filter((it) => it.sheet.id !== id);
        changed = true;
      } catch (err) { toast(p.item.sheet.code + " : " + err.message, "error"); }
      showUndo();
      draw();
    };
    const showUndo = () => {
      clear(undoBar);
      undoBar.hidden = !pending.size;
      if (!pending.size) return;
      const last = [...pending.values()].pop();
      undoBar.append(el("span", null, last.item.sheet.code + " supprimée" + (pending.size > 1 ? " (+" + (pending.size - 1) + ")" : "")),
        el("button", { type: "button", class: "btn btn-small", onclick: () => {
          clearTimeout(last.timer);
          pending.delete(last.item.sheet.id);
          state.id = last.item.sheet.id;
          showUndo();
          draw();
        } }, "Annuler"));
    };

    const close = async () => {
      document.removeEventListener("keydown", onKey, true);
      await flush();
      root.remove();
      document.body.classList.remove("dm-review-on");
      if (changed) done();
    };

    const current = () => {
      const items = list();
      let i = items.findIndex((it) => it.sheet.id === state.id);
      if (i < 0) i = 0;
      return { items, i, it: items[i] };
    };
    const go = (step) => {
      const { items, i } = current();
      if (!items.length) return;
      state.id = items[Math.max(0, Math.min(items.length - 1, i + step))].sheet.id;
      draw();
    };
    const after = (id) => {  // the next one in the list, else the previous one
      const items = list();
      const i = items.findIndex((it) => it.sheet.id === id);
      const next = items[i + 1] || items[i - 1];
      state.id = next ? next.sheet.id : null;
    };

    const review = async (action) => {
      const { it, i } = current();
      if (!it || !editable || it.concept.frozen) return;
      try {
        const r = await api.post(D.base(ctx) + "/sheets/" + it.sheet.id + "/review", { action });
        Object.assign(it.sheet, r.sheet);
        changed = true;
        if (action !== "reopen") {  // on to the next one; when the sheet left the list (« À revoir »), the next slid into its place
          const items = list();
          const still = items.findIndex((x) => x.sheet.id === it.sheet.id);
          const next = still >= 0 ? items[still + 1] || items[still] : items[i] || items[items.length - 1];
          state.id = next ? next.sheet.id : null;
        }
        draw();
      } catch (err) { toast(err.message, "error"); }
    };
    const remove = () => {
      const { it, i } = current();
      if (!it || !editable || it.concept.frozen) return;
      if (it.sheet.status === "selected") { toast(it.sheet.code + " est retenue par une matrice de Pugh : elle ne peut pas être supprimée.", "error"); return; }
      after(it.sheet.id);
      pending.set(it.sheet.id, { item: it, index: i, timer: setTimeout(() => send(it.sheet.id), UNDO_MS) });
      showUndo();
      draw();
    };
    const edit = () => {
      const { it } = current();
      if (!it || !editable || it.concept.frozen) return;
      D.editSheet(ctx, it.sheet, async () => {
        const fresh = await api.get(D.base(ctx) + "/sheets");
        const map = new Map(fresh.sheets.map((s) => [s.id, s]));
        all.forEach((x) => { if (map.has(x.sheet.id)) Object.assign(x.sheet, map.get(x.sheet.id)); });
        changed = true;
        draw();
      });
    };

    function onKey(ev) {
      if (document.querySelector(".modal-backdrop")) return;  // the edit window has the keyboard
      const t = ev.target;
      if (ev.key === "Escape") { ev.preventDefault(); close(); return; }
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      const k = ev.key.toLowerCase();
      const run = { arrowright: () => go(1), arrowleft: () => go(-1), g: () => review("keep"), e: () => review("drop"),
        delete: remove, m: edit }[k];
      if (run && !ev.ctrlKey && !ev.metaKey && !ev.altKey) { ev.preventDefault(); run(); }
    }

    const picture = (s) => {
      const own = s.attachment_id && String(s.file_mime || "").startsWith("image/");
      const pdfOnly = s.attachment_id && !own;
      const v = "?v=" + encodeURIComponent(s.updated_at || "");
      if (pdfOnly) return el("a", { class: "btn", href: D.base(ctx) + "/sheets/" + s.id + "/file", target: "_blank", rel: "noopener" }, "Ouvrir le scan (PDF)");
      return el("img", { class: "dm-review-img", alt: "Feuille " + s.code,
        src: D.base(ctx) + "/sheets/" + s.id + (own ? "/file" : "/sheet.svg") + v });
    };
    const lines = (label, text, cls) => (text ? el("div", { class: "dm-review-field " + (cls || "") }, el("strong", null, label),
      String(text).split("\n").filter(Boolean).map((l) => el("div", null, l))) : null);

    function draw() {
      state.scope = scopeSel.value;
      state.filter = filterSel.value;
      const { items, i, it } = current();
      if (it) state.id = it.sheet.id;
      remember(ctx, { scope: state.scope, filter: state.filter, id: state.id });
      const scope = inScope();
      clear(counter);
      counter.append((items.length ? (i + 1) + " / " + items.length : "0 / 0") + " · vues " + scope.filter((x) => seen(x.sheet)).length
        + " / " + scope.length);
      clear(stage);
      clear(side);
      if (!it) {
        stage.append(el("p", { class: "muted" }, state.filter === "todo" ? "Tout est revu dans cette portée." : "Aucune feuille ici."));
        return;
      }
      const s = it.sheet;
      const frozen = it.concept.frozen;
      stage.append(picture(s));
      const status = { open: "Open", selected: "Selected", dropped: "Dropped" }[s.status] || s.status;
      side.append(
        el("div", { class: "dm-review-crumbs muted" }, it.branch ? "F" + it.branch.number + " " + it.branch.text : "Sans branche", " › ",
          it.concept.code + " " + (it.concept.initial_name || it.concept.name)),
        el("h2", null, el("span", { class: "dm-code" }, s.code), " ", s.title),
        el("div", { class: "dm-actions" },
          el("span", { class: "badge badge-neutral" }, { digital: "Numérique", ai: "IA", scan: "Scan" }[s.kind] || s.kind),
          el("span", { class: "badge " + (s.status === "dropped" ? "badge-off" : s.status === "selected" ? "badge-ok" : "badge-neutral") }, status),
          s.badge ? el("span", { class: "badge badge-warn" }, s.badge) : null,
          seen(s) ? el("span", { class: "badge badge-ok" }, "Vue" + (s.reviewer_name ? " · " + s.reviewer_name : "")) : null,
          frozen ? el("span", { class: "badge badge-ok" }, "Brique figée") : null),
        editable && !frozen ? el("div", { class: "dm-review-acts" },
          el("button", { type: "button", class: "btn btn-primary", onclick: () => review("keep") }, el("kbd", null, "G"), " Garder"),
          el("button", { type: "button", class: "btn", onclick: () => review("drop") }, el("kbd", null, "E"), " Écarter"),
          el("button", { type: "button", class: "btn btn-danger", disabled: s.status === "selected" ? "" : null, onclick: remove },
            el("kbd", null, "Suppr"), " Supprimer"),
          el("button", { type: "button", class: "btn", onclick: edit }, el("kbd", null, "M"), " Modifier"),
          seen(s) || s.status === "dropped" ? el("button", { type: "button", class: "btn btn-small", onclick: () => review("reopen") }, "Rouvrir") : null)
          : el("p", { class: "muted" }, frozen ? "Brique figée : lecture seule." : "Lecture seule."),
        lines("Principe", s.principle), lines("Description", s.description), lines("+", s.pros, "dm-review-pros"),
        lines("−", s.cons, "dm-review-cons"), lines("?", s.questions, "dm-review-q"));
    }

    scopeSel.addEventListener("change", () => { state.id = null; draw(); });
    filterSel.addEventListener("change", () => { state.id = null; draw(); });
    root.append(
      el("div", { class: "dm-review-bar" }, el("strong", null, "Revue des feuilles de concept"), scopeSel, filterSel, counter,
        el("span", { class: "dm-review-keys muted" }, "← → · G garder · E écarter · Suppr supprimer · M modifier · Échap"),
        el("button", { type: "button", class: "btn btn-small", onclick: close }, "Fermer")),
      el("div", { class: "dm-review-body" },
        el("button", { type: "button", class: "dm-review-nav", "aria-label": "Feuille précédente", onclick: () => go(-1) }, "‹"),
        stage, side,
        el("button", { type: "button", class: "dm-review-nav", "aria-label": "Feuille suivante", onclick: () => go(1) }, "›")),
      undoBar);
    document.body.append(root);
    document.body.classList.add("dm-review-on");
    document.addEventListener("keydown", onKey, true);
    draw();
  }

  D.openReview = open;
})();
