/* Diamond · « Revue » of the concept sheets (0.60.133, D-O-146): one sheet at a time, full screen, in the order of the tree
   (branch, brick, number: CB-6.9 before CB-6.10); « Suivant » on the last sheet of a branch goes on to the next branch.
   Scope: every branch, one branch or one brick; filter: all, to review (Open and not seen), dropped.
   ← / → previous / next · G keep (seen; a dropped sheet is back in the running) · E drop (« Dropped », seen) · Suppr delete (gone at
   once, « Annuler » for 5 s: the server is called only after) · M edit · R refine with the AI (0.60.135, D-O-148: « ↔ IA : feuilles
   de concept » on this one sheet) · Ctrl+Z undo the last keep, drop or delete · Échap close.
   0.60.134 (D-O-147): the list of a review is fixed when it starts (or when the scope or the filter changes): a sheet kept or dropped
   stays in it with its new status, so ← always goes back to it; a strip of every sheet of the list, by branch, coloured by status,
   jumps to any of them. Seen is shared by the team (concept_review.py); the place in the review is remembered in this browser for the
   Space. A frozen brick is read only; a sheet retained by a Pugh matrix cannot be dropped or deleted. */
(function () {
  "use strict";

  const { api, el, clear, toast } = DA;
  const D = DA.diamond;
  const A = DA.agile;
  const UNDO_MS = 5000;
  const BAR_MS = 6000;
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
  const DONE = { keep: "gardée", drop: "écartée", reopen: "rouverte" };
  /* The action that puts a sheet back as it was (Ctrl+Z) */
  const reverse = (before) => (before.status === "dropped" ? "drop" : before.seen ? "keep" : "reopen");
  const chipState = (s) => (s.status === "selected" ? "selected" : s.status === "dropped" ? "dropped" : seen(s) ? "kept" : "todo");

  async function open(ctx, done, start) {
    const [data, cdata] = await Promise.all([api.get(D.base(ctx) + "/sheets"), api.get(D.base(ctx) + "/concepts")]);
    let all = ordered(data, cdata);
    if (!all.length) { toast("Aucune feuille de concept à revoir.", "info"); return; }
    const editable = A.canEdit(ctx);
    const kept = remembered(ctx);
    const state = { scope: (start && start.scope) || kept.scope || "all", filter: kept.filter || "all", id: (start && start.id) || kept.id };
    const pending = new Map();  // sheet id -> { timer, item }: deletions waiting for their 5 s
    const history = [];  // the last actions, for Ctrl+Z: { kind: "review", id, before } | { kind: "delete", id }
    let queue = [];  // the ids of the review's list, fixed until the scope or the filter changes
    let changed = false;
    let barTimer = null;

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

    const byId = () => new Map(all.map((it) => [it.sheet.id, it]));
    const inScope = () => all.filter((it) => state.scope === "all"
      || (state.scope[0] === "f" && it.branch && "f" + it.branch.id === state.scope)
      || (state.scope[0] === "c" && "c" + it.concept.id === state.scope));
    const rebuild = () => {
      state.scope = scopeSel.value;
      state.filter = filterSel.value;
      queue = inScope().filter((it) => !pending.has(it.sheet.id) && FILTERS[state.filter](it.sheet)).map((it) => it.sheet.id);
    };
    const items = () => {
      const map = byId();
      return queue.filter((id) => !pending.has(id) && map.has(id)).map((id) => map.get(id));
    };

    const counter = el("span", { class: "dm-review-count", role: "status" });
    const stage = el("div", { class: "dm-review-stage" });
    const side = el("div", { class: "dm-review-side" });
    const strip = el("div", { class: "dm-review-strip", role: "list", "aria-label": "Toutes les feuilles de la revue",
      "data-new": "0.60.134-review-strip" });
    const bar = el("div", { class: "dm-review-undo", hidden: true, role: "status" });
    const root = el("div", { class: "dm-review", role: "dialog", "aria-modal": "true", "aria-label": "Revue des feuilles de concept",
      "data-new": "0.60.133-review" });

    const say = (text, ms) => {  // the bar of the last action, with « Annuler »
      clearTimeout(barTimer);
      clear(bar);
      bar.hidden = !text;
      if (!text) return;
      bar.append(el("span", null, text), el("button", { type: "button", class: "btn btn-small", onclick: undo }, "Annuler"),
        el("span", { class: "dm-undo-hint" }, "Ctrl+Z"));
      if (ms) barTimer = setTimeout(() => say(""), ms);
    };

    const send = async (id) => {
      const p = pending.get(id);
      if (!p) return;
      pending.delete(id);
      try {
        await api.del(D.base(ctx) + "/sheets/" + id);
        all = all.filter((it) => it.sheet.id !== id);
        queue = queue.filter((x) => x !== id);
        changed = true;
      } catch (err) { toast(p.item.sheet.code + " : " + err.message, "error"); }
      if (!pending.size) say("");
      draw();
    };
    const flush = async () => {  // the deletions still waiting, sent now (closing the review)
      const ids = [...pending.keys()];
      ids.forEach((id) => clearTimeout(pending.get(id).timer));
      await Promise.all(ids.map((id) => send(id)));
    };
    const close = async () => {
      document.removeEventListener("keydown", onKey, true);
      clearTimeout(barTimer);
      await flush();
      root.remove();
      document.body.classList.remove("dm-review-on");
      if (changed) done();
    };

    const current = () => {
      const list = items();
      let i = list.findIndex((it) => it.sheet.id === state.id);
      if (i < 0) i = 0;
      return { list, i, it: list[i] };
    };
    const jump = (id) => { state.id = id; draw(); };
    const go = (step) => {
      const { list, i } = current();
      if (list.length) jump(list[Math.max(0, Math.min(list.length - 1, i + step))].sheet.id);
    };

    const post = async (it, action) => {
      const r = await api.post(D.base(ctx) + "/sheets/" + it.sheet.id + "/review", { action });
      Object.assign(it.sheet, r.sheet);
      changed = true;
    };
    const review = async (action) => {
      const { list, i, it } = current();
      if (!it || !editable || it.concept.frozen) return;
      const before = { status: it.sheet.status, seen: seen(it.sheet) };
      try {
        await post(it, action);
        history.push({ kind: "review", id: it.sheet.id, before });
        say(it.sheet.code + " " + DONE[action], BAR_MS);
        if (action !== "reopen" && list[i + 1]) state.id = list[i + 1].sheet.id;  // the list is fixed: on to the next one
        draw();
      } catch (err) { toast(err.message, "error"); }
    };
    const remove = () => {
      const { list, i, it } = current();
      if (!it || !editable || it.concept.frozen) return;
      if (it.sheet.status === "selected") { toast(it.sheet.code + " est retenue par une matrice de Pugh : elle ne peut pas être supprimée.", "error"); return; }
      const next = list[i + 1] || list[i - 1];
      state.id = next ? next.sheet.id : null;
      pending.set(it.sheet.id, { item: it, timer: setTimeout(() => send(it.sheet.id), UNDO_MS) });
      history.push({ kind: "delete", id: it.sheet.id });
      say(it.sheet.code + " supprimée" + (pending.size > 1 ? " (+" + (pending.size - 1) + " en attente)" : ""));
      draw();
    };
    async function undo() {
      const last = history.pop();
      if (!last) { say(""); return; }
      if (last.kind === "delete") {
        const p = pending.get(last.id);
        if (!p) { toast("Déjà supprimée : seule une sauvegarde du Space peut la rendre.", "error"); say(""); return; }
        clearTimeout(p.timer);
        pending.delete(last.id);
        say(p.item.sheet.code + " gardée (suppression annulée)", BAR_MS);
        jump(last.id);
        return;
      }
      const it = byId().get(last.id);
      if (!it) { say(""); return; }
      try {
        await post(it, reverse(last.before));
        say(it.sheet.code + " remise comme avant", BAR_MS);
        jump(last.id);
      } catch (err) { toast(err.message, "error"); }
    }
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

    const refine = () => {  // 0.60.135 (D-O-148): R, this sheet with the AI -- its text and its sketch, its code kept
      const { it } = current();
      if (!it || it.concept.frozen) return;
      D.openConceptRound(ctx, async () => {
        const fresh = await api.get(D.base(ctx) + "/sheets");
        const map = new Map(fresh.sheets.map((s) => [s.id, s]));
        all.forEach((x) => { if (map.has(x.sheet.id)) Object.assign(x.sheet, map.get(x.sheet.id)); });
        changed = true;
        draw();
      }, { scope: "s" + it.sheet.id });
    };

    function onKey(ev) {
      if (document.querySelector(".modal-backdrop")) return;  // the edit window has the keyboard
      const t = ev.target;
      if (ev.key === "Escape") { ev.preventDefault(); close(); return; }
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      const k = ev.key.toLowerCase();
      if (k === "z" && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); undo(); return; }
      const run = { arrowright: () => go(1), arrowleft: () => go(-1), home: () => go(-1e6), end: () => go(1e6),
        g: () => review("keep"), e: () => review("drop"), delete: remove, m: edit, r: refine }[k];
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

    /* The actions of a sheet, by its state: a dropped sheet offers to come back */
    function actions(s, frozen) {
      if (!editable || frozen) return el("p", { class: "muted" }, frozen ? "Brique figée : lecture seule." : "Lecture seule.");
      const dropped = s.status === "dropped";
      const keptOne = seen(s) && !dropped;
      return el("div", { class: "dm-review-acts" },
        el("button", { type: "button", class: "btn btn-primary", "data-new": dropped ? "0.60.134-review-back" : null, onclick: () => review("keep") },
          el("kbd", null, "G"), dropped ? " Remettre en course" : keptOne ? " ✓ Gardée" : " Garder"),
        dropped ? null : el("button", { type: "button", class: "btn", disabled: s.status === "selected" ? "" : null, onclick: () => review("drop") },
          el("kbd", null, "E"), " Écarter"),
        el("button", { type: "button", class: "btn btn-danger", disabled: s.status === "selected" ? "" : null, onclick: remove },
          el("kbd", null, "Suppr"), " Supprimer"),
        el("button", { type: "button", class: "btn", onclick: edit }, el("kbd", null, "M"), " Modifier"),
        el("button", { type: "button", class: "btn", "data-new": "0.60.135-review-refine", onclick: refine }, el("kbd", null, "R"), " Raffiner avec l'IA"),
        seen(s) || dropped ? el("button", { type: "button", class: "btn btn-small", onclick: () => review("reopen") }, "Rouvrir (à revoir)") : null);
    }

    function drawStrip(list, it) {
      clear(strip);
      let branch;
      list.forEach((x) => {
        const b = x.branch ? x.branch.id : 0;
        if (b !== branch) {
          branch = b;
          strip.append(el("span", { class: "dm-review-strip-branch" }, x.branch ? "F" + x.branch.number : "—"));
        }
        const s = x.sheet;
        strip.append(el("button", { type: "button", role: "listitem", class: "dm-chip dm-chip-" + chipState(s) + (x === it ? " dm-chip-on" : ""),
          title: s.code + " · " + s.title, "aria-current": x === it ? "true" : null, onclick: () => jump(s.id) }, s.code));
      });
      const on = strip.querySelector(".dm-chip-on");
      if (on && on.scrollIntoView) on.scrollIntoView({ block: "nearest", inline: "center" });
    }

    function draw() {
      const { list, i, it } = current();
      if (it) state.id = it.sheet.id;
      remember(ctx, { scope: state.scope, filter: state.filter, id: state.id });
      const scope = inScope().filter((x) => !pending.has(x.sheet.id));
      clear(counter);
      counter.append((list.length ? (i + 1) + " / " + list.length : "0 / 0") + " · vues " + scope.filter((x) => seen(x.sheet)).length
        + " / " + scope.length + " · écartées " + scope.filter((x) => x.sheet.status === "dropped").length);
      clear(stage);
      clear(side);
      drawStrip(list, it);
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
        actions(s, frozen),
        lines("Principe", s.principle), lines("Description", s.description), lines("+", s.pros, "dm-review-pros"),
        lines("−", s.cons, "dm-review-cons"), lines("?", s.questions, "dm-review-q"));
    }

    const restart = () => { state.id = null; rebuild(); draw(); };
    scopeSel.addEventListener("change", restart);
    filterSel.addEventListener("change", restart);
    root.append(
      el("div", { class: "dm-review-bar" }, el("strong", null, "Revue des feuilles de concept"), scopeSel, filterSel, counter,
        el("span", { class: "dm-review-keys muted" }, "← → · G garder · E écarter · Suppr supprimer · M modifier · Ctrl+Z annuler · Échap"),
        el("button", { type: "button", class: "btn btn-small", onclick: close }, "Fermer")),
      el("div", { class: "dm-review-body" },
        el("button", { type: "button", class: "dm-review-nav", "aria-label": "Feuille précédente", onclick: () => go(-1) }, "‹"),
        stage, side,
        el("button", { type: "button", class: "dm-review-nav", "aria-label": "Feuille suivante", onclick: () => go(1) }, "›")),
      strip, bar);
    document.body.append(root);
    document.body.classList.add("dm-review-on");
    document.addEventListener("keydown", onKey, true);
    rebuild();
    draw();
  }

  D.openReview = open;
})();
