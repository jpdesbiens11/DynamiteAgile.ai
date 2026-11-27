/* Diamond · concept sheets, the tools of « Feuilles de concept » (0.60.125, D-O-138):
   - the sheet on the platform's template (the server draws it: /sheets/<id>/sheet.svg and .pdf); « PNG » turns the SVG into a
     picture in the browser (a canvas: nothing leaves the page);
   - « Importer un lot (.zip) »: the cards (.md) of a brainstorm with the picture and the PDF of each sheet; preview, then import;
     0.60.129 (D-O-142): a file named by the code of an existing sheet (CB-1.1_croquis.png) goes on that sheet; one ticked line per
     sheet or file; a sheet with its own picture is shown and exported (PNG, PDF) as that picture;
     0.60.131 (D-O-144): the reponse.json of the .zip is read (new code → « ai » sheet on the template, existing code → updated),
     and the import ends on its report, one line per sheet or file (created, updated, attached, nothing to do and why);
   - « IA : une branche »: the prompt of every brick to define under one secondary function of the tree, to iterate with the
     assistant branch by branch; its answer comes back through « Importer la réponse de l'IA » (concept_ai.js). */
(function () {
  "use strict";

  const { api, el, clear, field, toast, modal } = DA;
  const D = DA.diamond;

  const sheetUrl = (ctx, s, ext) => D.base(ctx) + "/sheets/" + s.id + "/sheet." + ext;
  const fileUrl = (ctx, s, which) => D.base(ctx) + "/sheets/" + s.id + "/file" + (which ? "?which=" + which : "");
  const slug = (s) => s.code + "_" + String(s.title || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 50);

  /* The SVG of the template drawn at 2x on a canvas, saved as PNG; or the sheet's own picture at its size (0.60.129) */
  async function savePng(ctx, s, own) {
    try {
      const img = new Image();  // the same-origin URL itself: the page's CSP refuses a blob: image, and the canvas stays clean
      await new Promise((ok, ko) => { img.onload = ok; img.onerror = () => ko(new Error("Feuille illisible : rechargez la page.")); img.src = own ? fileUrl(ctx, s) : sheetUrl(ctx, s, "svg"); });
      const canvas = document.createElement("canvas");
      canvas.width = own ? img.naturalWidth : 2246;
      canvas.height = own ? img.naturalHeight : 1588;
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob((blob) => {
        const a = el("a", { href: URL.createObjectURL(blob), download: slug(s) + ".png" });
        document.body.append(a);
        a.click();
        a.remove();
      }, "image/png");
    } catch (err) { toast(err.message, "error"); }
  }

  /* The picture of a sheet in its card: the deposited picture, else the sheet drawn on the template; and its files */
  function visual(ctx, s) {
    const picture = s.attachment_id && String(s.file_mime || "").startsWith("image/");
    const src = picture ? fileUrl(ctx, s) : sheetUrl(ctx, s, "svg");
    const thumb = s.attachment_id && !picture ? null
      : el("a", { href: src, target: "_blank", rel: "noopener", class: "dm-sheet-visual" },
        el("img", { class: "dm-sheet-scan", src, alt: "Feuille " + s.code, loading: "lazy" }));
    const links = el("div", { class: "dm-actions dm-sheet-files", "data-new": "0.60.125-sheet-files" },
      s.attachment_id && !picture ? el("a", { class: "btn btn-small", href: fileUrl(ctx, s), target: "_blank", rel: "noopener" }, "Ouvrir le scan (PDF)") : null,
      s.pdf_id ? el("a", { class: "btn btn-small", href: fileUrl(ctx, s, "pdf"), target: "_blank", rel: "noopener" }, picture ? "PDF joint" : "PDF") : null,
      !s.attachment_id || picture ? el("button", { type: "button", class: "btn btn-small", "data-new": picture ? "0.60.129-sheet-image-export" : null,
        "data-tip": picture ? "L'image de la feuille" : "La feuille au gabarit, en image", onclick: () => savePng(ctx, s, picture) }, "PNG") : null,
      !s.attachment_id || picture ? el("a", { class: "btn btn-small", href: sheetUrl(ctx, s, "pdf"),
        "data-tip": picture ? "L'image de la feuille, A4 paysage" : "La feuille au gabarit, A4 paysage" }, "PDF") : null);
    return [thumb, links];
  }

  /* « Importer un lot (.zip) » */
  function openImport(ctx, bricks, done) {
    const file = el("input", { type: "file", accept: ".zip,application/zip", "aria-label": "Fichier .zip" });
    const target = el("select", null, el("option", { value: "" }, "Selon le code de chaque feuille (CB-n.m → brique CB-n)"),
      bricks.map((c) => el("option", { value: c.id }, c.code + " " + (c.initial_name ? "« " + c.initial_name + " » " : "") + c.name)));
    const extras = el("input", { type: "checkbox" });
    const result = el("div", { role: "status" });
    const go = el("button", { type: "button", class: "btn btn-primary", disabled: "" }, "Importer");
    const ticks = new Map();  // 0.60.129 (D-O-142): key of a line → its checkbox
    const skipped = () => [...ticks].filter(([, box]) => !box.checked).map(([key]) => key);
    const url = (mode) => D.base(ctx) + "/sheets/import?mode=" + mode + (target.value ? "&cid=" + target.value : "") + (extras.checked ? "&extras=1" : "")
      + (mode === "apply" && skipped().length ? "&skip=" + encodeURIComponent(JSON.stringify(skipped())) : "");
    const refresh = () => { go.disabled = ![...ticks.values()].some((box) => box.checked); };
    const invalidate = () => { go.disabled = true; ticks.clear(); clear(result); };
    [file, target, extras].forEach((x) => x.addEventListener("change", invalidate));
    const check = async () => {
      clear(result);
      if (!file.files.length) { result.append(el("p", { class: "form-error" }, "Choisissez le .zip.")); return; }
      try {
        const r = await api.upload(url("preview"), file.files[0]);
        ticks.clear();
        result.append(preview(r, ticks, refresh));
        refresh();
      } catch (err) { result.append(el("p", { class: "form-error", role: "alert" }, err.message)); }
    };
    let close = null;
    go.addEventListener("click", async () => {
      go.disabled = true;
      try {
        const r = await api.upload(url("apply"), file.files[0]);
        toast(r.created + " feuille(s) créée(s), " + (r.updated || 0) + " mise(s) à jour, " + r.attached
          + " fichier(s) posé(s) sur des feuilles existantes. Sauvegarde du Space : " + r.backup + ".", "success");
        ticks.clear();
        clear(result);
        result.append(report(r));  // 0.60.131 (D-O-144): what happened to each line, before closing
        done();
      } catch (err) { go.disabled = false; toast(err.message, "error"); }
    });
    close = modal("Importer des feuilles de concept", el("div", { class: "ag-form", "data-new": "0.60.125-sheets-import" },
      el("p", { class: "muted", "data-new": "0.60.131-sheets-json" }, "Un reponse.json ({\"sheets\": […]}, la réponse de « ↔ IA ») "
        + "dans le .zip est lu : un code nouveau (CB-6.6) crée la feuille IA avec tout son texte et son croquis dessiné sur le gabarit ; "
        + "un code existant met sa feuille à jour, sans doublon."),
      el("p", { class: "muted" }, "Un .zip : les cartes au format de la plateforme (.md : « ## CB-3.2 — Titre », « **Principle:** … », "
        + "la description, puis une ligne par « + », « − » et « ? », « **Badge:** … ») et l'image (PNG, JPEG) et le PDF de chaque feuille, "
        + "nommés par leur code (CB-3.2_bras.png). Rien n'est écrasé : une feuille du même titre déjà dans la brique est laissée."),
      el("p", { class: "muted", "data-new": "0.60.129-sheets-attach" }, "Une image ou un PDF sans carte dont le nom commence par le code d'une "
        + "feuille existante (CB-1.1_croquis_ia.png) va sur cette feuille : il remplace son image (l'ancienne reste dans les pièces jointes), "
        + "aucune feuille n'est créée. Une sauvegarde du Space est faite avant d'importer."),
      field("Fichier .zip", file), field("Brique", target),
      el("label", { class: "check" }, extras, "Importer aussi les images sans numéro de feuille (synthèse d'une brique) comme feuilles"),
      result, el("div", { class: "form-actions" }, el("button", { type: "button", class: "btn", onclick: () => close() }, "Annuler"),
        el("button", { type: "button", class: "btn", onclick: check }, "Vérifier"), go)));
    document.querySelectorAll(".modal").forEach((m) => m.classList.add("modal-wide"));
  }

  /* The preview: one line per sheet to create or file to put on a sheet, ticked (0.60.129, D-O-142) */
  function preview(r, ticks, refresh) {
    const label = { new: "Nouvelle", update: "Mise à jour", attach: "Sur la feuille", exists: "Déjà là", refused: "Refusée" };
    const badge = { new: "badge-ok", update: "badge-warn", attach: "badge-info", exists: "badge-neutral", refused: "badge-off" };
    const what = (e) => {
      if (e.status === "update") return "mise à jour de " + e.code + " : " + (e.changes || []).join(", ");
      if (!e.action) return e.status === "new" ? "nouvelle feuille " + (e.kind === "scan" ? "Scan" : e.kind === "digital" ? "numérique" : "IA") : "—";
      return (e.action === "pdf" ? "PDF" : "image") + " → " + e.code + (e.replaces ? " (remplace " + (e.action === "pdf" ? "le PDF actuel)" : "l'image actuelle)") : "");
    };
    const box = (e) => {
      if (!["new", "update", "attach"].includes(e.status)) return null;
      const b = el("input", { type: "checkbox", checked: true, "aria-label": "Importer " + (e.files[0] || e.title) });
      b.addEventListener("change", refresh);
      ticks.set(e.key, b);
      return b;
    };
    const all = el("input", { type: "checkbox", checked: true, "aria-label": "Tout cocher" });
    all.addEventListener("change", () => { ticks.forEach((b) => { b.checked = all.checked; }); refresh(); });
    return el("div", { class: "dm-import-preview", "data-new": "0.60.129-sheets-attach-preview" },
      el("p", null, el("strong", null, "Aperçu : "), r.cards + " carte(s), " + r.files + " fichier(s) — " + r.counts.new + " nouvelle(s) feuille(s), "
        + (r.counts.update || 0) + " mise(s) à jour, " + r.counts.attach + " fichier(s) sur des feuilles existantes, " + r.counts.exists + " déjà là, " + r.counts.refused + " refusé(s)."),
      (r.warnings || []).length ? el("ul", { class: "dm-import-warnings", role: "note" }, r.warnings.map((w) => el("li", null, "⚠ " + w))) : null,
      r.entries.length ? DA.table([all, "Fichier ou feuille", "Action", "Brique", "Statut"], r.entries.map((e) => el("tr", null,
        el("td", null, box(e)),
        el("td", null, e.code ? el("span", { class: "dm-code" }, e.code + " ") : null, e.action ? e.files[0] : e.title,
          !e.action && (e.files || []).length ? el("div", { class: "muted" }, e.files.join(", ")) : null),
        el("td", null, what(e)), el("td", null, e.brick || "—"),
        el("td", null, el("span", { class: "badge " + badge[e.status] }, label[e.status]), e.reason ? el("span", { class: "muted" }, " " + e.reason) : null,
          e.warning ? el("div", { class: "muted" }, "⚠ " + e.warning) : null)))) : null,
      r.left.length ? el("p", { class: "muted" }, "Laissés de côté (sans code de feuille) : " + r.left.join(", ") + ".") : null);
  }

  /* The report of an import (0.60.131, D-O-144): one line per sheet or file, what was done */
  function report(r) {
    return el("div", { class: "dm-import-preview", "data-new": "0.60.131-sheets-import-report" },
      el("p", { class: "up-ok" }, "✓ Import terminé : " + r.created + " créée(s), " + (r.updated || 0) + " mise(s) à jour, " + r.attached
        + " fichier(s) posé(s). Sauvegarde du Space : " + r.backup + "."),
      (r.warnings || []).length ? el("ul", { class: "dm-import-warnings", role: "note" }, r.warnings.map((w) => el("li", null, "⚠ " + w))) : null,
      DA.table(["Fichier ou feuille", "Brique", "Résultat"], r.entries.map((e) => el("tr", null,
        el("td", null, e.code ? el("span", { class: "dm-code" }, e.code + " ") : null, e.action ? e.files[0] : e.title),
        el("td", null, e.brick || "—"), el("td", null, e.outcome || "—")))));
  }

  /* « IA : une branche » */
  function openBranch(ctx, data, done, fid) {  // fid: 0.60.128 (D-O-141), the branch chosen from its block
    const fns = data.functions.filter((f) => f.in_tree && f.level === 2);
    const under = (root) => {
      const ids = new Set([root.id]);
      let grew = true;
      while (grew) { grew = false; data.functions.forEach((f) => { if (!ids.has(f.id) && ids.has(f.parent_id)) { ids.add(f.id); grew = true; } }); }
      return data.concepts.filter((c) => c.function_ids.some((id) => ids.has(id)));
    };
    const pick = el("select", { "aria-label": "Branche" }, fns.map((f) => {
      const n = under(f);
      return el("option", { value: f.id, disabled: !n.length }, "F" + f.number + " " + f.text + " — " + n.length + " brique(s), "
        + n.filter((c) => c.kind === "to_define").length + " à définir");
    }));
    if (fid) pick.value = String(fid);
    const out = el("div");
    let close = null;
    const copy = async () => {
      clear(out);
      let res;
      try { res = await api.get(D.base(ctx) + "/concepts/branch-prompt?fid=" + pick.value); } catch (err) { out.append(el("p", { class: "form-error" }, err.message)); return; }
      let ok = false;
      try { await navigator.clipboard.writeText(res.prompt); ok = true; } catch (err) { ok = false; }
      const area = el("textarea", { rows: 8, readonly: true, class: "dm-story-ai-text", "aria-label": "Prompt" }, res.prompt);
      out.append(el("p", { class: ok ? "up-ok" : "muted" }, (ok ? "✓ Prompt copié" : "Copiez ce prompt") + " (" + res.bricks + " brique(s)) : "
        + "collez-le dans votre assistant, répondez à ses questions, itérez, puis importez son bloc JSON."), area);
      area.select();
    };
    close = modal("IA : les feuilles d'une branche", el("div", { class: "ag-form", "data-new": "0.60.125-sheets-branch-ai" },
      el("p", { class: "muted" }, "Une branche de l'arbre (une fonction secondaire et ses fonctions) à la fois : l'assistant propose des "
        + "feuilles pour chacune de ses briques à définir ; la plateforme les dessine sur son gabarit."),
      fns.length ? field("Branche", pick) : el("p", { class: "muted" }, "Aucune fonction secondaire dans l'arbre."), out,
      el("div", { class: "form-actions" }, el("button", { type: "button", class: "btn", onclick: () => close() }, "Fermer"),
        fns.length ? el("button", { type: "button", class: "btn", onclick: copy }, "1 · Copier le prompt") : null,
        el("button", { type: "button", class: "btn btn-primary", onclick: () => { close(); D.aiImportDialog(ctx, done); } }, "2 · Importer la réponse"))));
    document.querySelectorAll(".modal").forEach((m) => m.classList.add("modal-wide"));
  }

  Object.assign(D, { sheetVisual: visual, openSheetImport: openImport, openBranchAi: openBranch });
})();
