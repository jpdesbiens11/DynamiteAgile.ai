/* Diamond · « ↔ IA : feuilles de concept » (0.60.132, D-O-145): the only AI tool of « Feuilles de concept ».
   1 · Vers l'IA: one branch of the tree or all of them; the prompt shown in full in a box, « Copier le prompt »; the context .zip
       (contexte.json, the sketches and PDF of the sheets already drawn, PROMPT.md) when the scope has sheets.
   2 · Retour de l'IA: the .zip it hands back (reponse.json + images/<code>_*.png, PDF optional), or its reponse.json alone, applied at
       once -- a backup of the Space first, new codes created on the template, existing codes updated -- then the report, one line per
       sheet. A creativity session may go round four or five times: each round starts again from the context of the last one. */
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

  async function open(ctx, done) {
    const base = D.base(ctx) + "/concepts/round";
    const editable = A.canEdit(ctx);
    const pick = el("select", { "aria-label": "Branche", "data-new": "0.60.132-round-scope" }, el("option", { value: "all" }, "Toutes les branches"));
    const facts = el("p", { class: "muted", role: "status" });
    const box = el("textarea", { rows: 14, readonly: true, class: "dm-story-ai-text", "aria-label": "Prompt pour l'assistant IA" });
    const copy = el("button", { type: "button", class: "btn btn-primary" }, "Copier le prompt");
    const context = el("a", { class: "btn", download: "", hidden: true, "data-new": "0.60.132-round-context" }, "Télécharger le contexte (.zip)");
    const file = el("input", { type: "file", accept: ".zip,.json,application/zip,application/json", "aria-label": "Fichier .zip de l'IA" });
    const go = el("button", { type: "button", class: "btn btn-primary", disabled: "" }, "Importer");
    const result = el("div", { role: "status" });
    let filled = false;

    const load = async () => {
      clear(facts);
      box.value = "";
      context.hidden = true;
      copy.disabled = true;
      let r;
      try { r = await api.get(base + "?fid=" + encodeURIComponent(pick.value)); } catch (err) { facts.append(err.message); return; }
      if (!filled) {
        r.branches.forEach((b) => pick.append(el("option", { value: b.id, disabled: !b.bricks },
          b.label + " — " + b.bricks + " brique(s), " + b.to_define + " à définir")));
        filled = true;
      }
      if (r.error) { facts.append(el("span", { class: "form-error" }, r.error)); return; }
      facts.append(r.bricks + " brique(s) · " + r.to_define + " à définir · " + r.sheets + " feuille(s) déjà dessinée(s)"
        + (r.files ? " · " + r.files + " croquis ou PDF dans le contexte" : "")
        + ((r.frozen || []).length ? " · figées, laissées de côté : " + r.frozen.join(", ") : ""));
      box.value = r.prompt;
      copy.disabled = false;
      if (r.sheets) {
        context.href = base + "/context.zip?fid=" + encodeURIComponent(pick.value);
        context.hidden = false;
      }
    };
    pick.addEventListener("change", load);
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
        if (r.imported) { toast(r.created + " feuille(s) créée(s), " + r.updated + " mise(s) à jour.", "success"); done(); load(); }
      } catch (err) { result.append(el("p", { class: "form-error", role: "alert" }, err.message)); }
      go.disabled = !file.files.length;
    });

    modal("↔ IA : feuilles de concept", el("div", { class: "ag-form", "data-new": "0.60.132-round" },
      el("h3", null, "1 · Vers l'IA"),
      el("p", { class: "muted" }, "Choisissez une branche ou toutes les branches, copiez le prompt et collez-le dans votre assistant IA, "
        + "avec le fichier de contexte s'il y a déjà des feuilles (leurs croquis et PDF)."),
      field("Branche", pick), facts, box,
      el("div", { class: "form-actions" }, copy, context),
      editable ? el("h3", null, "2 · Retour de l'IA") : null,
      editable ? el("p", { class: "muted" }, "Déposez le .zip rendu par l'assistant (reponse.json et images/<code>_….png ; PDF facultatif), "
        + "ou son reponse.json seul. L'import se fait d'un coup : une sauvegarde du Space d'abord, chaque code nouveau crée sa feuille "
        + "dessinée sur le gabarit, chaque code existant met sa feuille à jour. Recommencez autant de tours que la séance le demande.") : null,
      editable ? field("Fichier de l'IA", file) : null,
      editable ? el("div", { class: "form-actions" }, go) : null,
      result));
    document.querySelectorAll(".modal").forEach((m) => m.classList.add("modal-wide"));
    load();
  }

  D.openConceptRound = open;
})();
