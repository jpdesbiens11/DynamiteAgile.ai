/* Diamond · « ↔ IA : feuilles de concept » (0.60.132, D-O-145): the one AI tool of the concept sheets -- an idea is its text AND its
   sketch, so it travels as a .zip both ways.
   1 · Vers l'IA: the scope -- all the branches, one branch, one brick, or one sheet to refine (0.60.135, D-O-148: opened from the
       page of a brick, from a sheet's card, from « ▶ Revue » with R, or from the morphological chart); the prompt shown in full in a
       box, « Copier le prompt »; the context .zip (contexte.json, the sketches and PDF, PROMPT.md) when the scope has sheets.
   2 · Retour de l'IA: the .zip it hands back (reponse.json + images/<code>_*.png, PDF optional), or its reponse.json alone, applied at
       once -- a backup of the Space first, new codes created on the template, existing codes updated, duplicates refused -- then
       the report, one line per sheet. A creativity session may go round four or five times: each round starts again from the
       context of the last one. */
(function () {
  "use strict";

  const { api, el, clear, field, toast, modal } = DA;
  const D = DA.diamond;
  const A = DA.agile;

  function report(r) {
    const label = { new: "Créée", update: "Mise à jour", attach: "Fichier posé", exists: "Inchangée", refused: "Refusée" };
    const badge = { new: "badge-ok", update: "badge-warn", attach: "badge-ok", exists: "badge-neutral", refused: "badge-off" };
    return el("div", { class: "dm-import-preview", "data-new": "0.60.132-round-report" },
      el("p", { class: r.imported ? "up-ok" : "muted" }, r.imported
        ? "✓ Import terminé : " + r.created + " créée(s), " + r.updated + " mise(s) à jour, " + r.attached + " fichier(s) posé(s). "
          + "Sauvegarde du Space : " + r.backup + "."
        : "Rien à changer : ce .zip est déjà dans le Space (ou ses feuilles sont refusées, voir les raisons)."),
      (r.warnings || []).length ? el("ul", { class: "dm-import-warnings", role: "note" }, r.warnings.map((w) => el("li", null, "⚠ " + w))) : null,
      r.entries.length ? DA.table(["Feuille", "Brique", "Résultat"], r.entries.map((e) => el("tr", null,
        el("td", null, e.code ? el("span", { class: "dm-code" }, e.code + " ") : null, e.action ? e.files[0] : e.title),
        el("td", null, e.brick || "—"),
        el("td", null, el("span", { class: "badge " + (badge[e.status] || "badge-neutral") }, label[e.status] || e.status), " ",
          el("span", { class: "muted" }, e.outcome === "créée " + e.code ? "" : e.outcome || e.reason || ""), e.warning ? el("div", { class: "muted" }, "⚠ " + e.warning) : null)))) : null);
  }

  /* The choices of the scope: all, the branches, the bricks, and the sheet being refined (when there is one) */
  function fill(pick, r) {
    clear(pick);
    pick.append(el("option", { value: "all" }, "Toutes les branches"),
      el("optgroup", { label: "Une branche" }, r.branches.map((b) => el("option", { value: "f" + b.id, disabled: !b.bricks },
        b.label + " — " + b.bricks + " brique(s), " + b.to_define + " à définir"))),
      el("optgroup", { label: "Une brique", "data-new": "0.60.135-round-brick" }, (r.brick_list || []).map((c) =>
        el("option", { value: "c" + c.id, disabled: c.frozen }, c.label + " — " + c.sheets + " feuille(s)" + (c.frozen ? " · figée" : "")))),
      r.sheet ? el("optgroup", { label: "Une feuille, à raffiner", "data-new": "0.60.135-round-sheet" },
        el("option", { value: "s" + r.sheet.id }, r.sheet.code + " « " + r.sheet.title + " »")) : null);
    pick.value = r.key || "all";
  }

  async function open(ctx, done, opts) {
    const base = D.base(ctx) + "/concepts/round";
    const editable = A.canEdit(ctx);
    let key = (opts && opts.scope) || "all";
    let sheet = null;  // kept in the list once chosen: switching to its brick and back stays possible
    const pick = el("select", { "aria-label": "Portée", "data-new": "0.60.132-round-scope" });
    const facts = el("p", { class: "muted", role: "status" });
    const hint = el("p", { class: "dm-ai-note", hidden: true, "data-new": "0.60.135-round-refine" });
    const box = el("textarea", { rows: 14, readonly: true, class: "dm-story-ai-text", "aria-label": "Prompt pour l'assistant IA" });
    const copy = el("button", { type: "button", class: "btn btn-primary" }, "Copier le prompt");
    const context = el("a", { class: "btn", download: "", hidden: true, "data-new": "0.60.132-round-context" }, "Télécharger le contexte (.zip)");
    const file = el("input", { type: "file", accept: ".zip,.json,application/zip,application/json", "aria-label": "Fichier .zip de l'IA" });
    const go = el("button", { type: "button", class: "btn btn-primary", disabled: "" }, "Importer");
    const result = el("div", { role: "status" });

    const load = async () => {
      clear(facts);
      box.value = "";
      context.hidden = true;
      copy.disabled = true;
      let r;
      try { r = await api.get(base + "?scope=" + encodeURIComponent(key)); } catch (err) { facts.append(el("span", { class: "form-error" }, err.message)); return; }
      sheet = r.sheet || sheet;
      fill(pick, Object.assign({}, r, { sheet, key }));
      hint.hidden = key[0] !== "s";
      if (sheet && key[0] === "s") {
        hint.textContent = "Raffiner " + sheet.code + " : l'IA garde son code, reprend son texte et redessine son croquis ; le contexte "
          + "porte son image actuelle et le texte des autres feuilles de " + sheet.brick + " (pour ne rien proposer deux fois).";
      }
      if (r.error) { facts.append(el("span", { class: "form-error" }, r.error)); return; }
      facts.append(r.scope + " · " + r.bricks + " brique(s) · " + r.to_define + " à définir · " + r.sheets + " feuille(s) déjà dessinée(s)"
        + (r.files ? " · " + r.files + " croquis ou PDF dans le contexte" : "")
        + ((r.frozen || []).length ? " · figées, laissées de côté : " + r.frozen.join(", ") : ""));
      box.value = r.prompt;
      copy.disabled = false;
      if (r.sheets) {
        context.href = base + "/context.zip?scope=" + encodeURIComponent(key);
        context.hidden = false;
      }
    };
    pick.addEventListener("change", () => { key = pick.value; load(); });
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(box.value); toast("Prompt copié : collez-le dans votre assistant IA.", "success"); }
      catch (err) { box.select(); toast("Copiez le texte sélectionné (Ctrl + C).", "info"); }
    });
    file.addEventListener("change", () => { go.disabled = !file.files.length; clear(result); });
    go.addEventListener("click", async () => {
      go.disabled = true;
      clear(result);
      try {
        const r = await api.upload(base + "/import", file.files[0]);
        result.append(report(r));
        if (r.imported) { toast(r.created + " feuille(s) créée(s), " + r.updated + " mise(s) à jour.", "success"); if (done) done(); load(); }
      } catch (err) { result.append(el("p", { class: "form-error", role: "alert" }, err.message)); }
      go.disabled = !file.files.length;
    });

    modal("↔ IA : feuilles de concept", el("div", { class: "ag-form", "data-new": "0.60.132-round" },
      el("h3", null, "1 · Vers l'IA"),
      el("p", { class: "muted" }, "Choisissez la portée : toutes les branches, une branche, une brique, ou une feuille à raffiner. Copiez "
        + "le prompt et collez-le dans votre assistant IA, avec le fichier de contexte s'il y a déjà des feuilles (leurs croquis et PDF). "
        + "Une idée est complète avec son texte et son croquis : l'IA rend les deux dans un .zip."),
      field("Portée", pick), hint, facts, box,
      el("div", { class: "form-actions" }, copy, context),
      editable ? el("h3", null, "2 · Retour de l'IA") : null,
      editable ? el("p", { class: "muted" }, "Déposez le .zip rendu par l'assistant (reponse.json et images/<code>_….png ; PDF facultatif), "
        + "ou son reponse.json seul. L'import se fait d'un coup : une sauvegarde du Space d'abord, chaque code nouveau crée sa feuille "
        + "dessinée sur le gabarit, chaque code existant met sa feuille à jour, un doublon (même titre ou même principe dans la brique) "
        + "est refusé. Recommencez autant de tours que la séance le demande.") : null,
      editable ? field("Fichier de l'IA", file) : null,
      editable ? el("div", { class: "form-actions" }, go) : null,
      result));
    document.querySelectorAll(".modal").forEach((m) => m.classList.add("modal-wide"));
    load();
  }

  /** The button that opens the round on a scope: "all", "f<id>", "c<id>" or "s<id>" (0.60.135, D-O-148). */
  D.roundButton = function (ctx, scope, done, label, small) {
    return el("button", { type: "button", class: "btn " + (small === false ? "" : "btn-small"), "data-new": "0.60.135-round-button",
      "data-tip": scope[0] === "s" ? "Raffiner cette feuille avec l'IA : son texte et son croquis, son code gardé"
        : "Le prompt et le contexte pour votre assistant IA, puis le .zip qu'il rend (texte et croquis de chaque feuille)",
      onclick: () => open(ctx, done, { scope }) }, label || "↔ IA : feuilles de concept");
  };
  D.openConceptRound = open;
})();
