/* Diamond · concept sheets (0.60.105, D-O-117). Under a brick (concept_page.js): its sheets as cards -- CB-3.1, title, principle,
   pros and cons, the scan of a paper sheet shown as an image (or a PDF link) -- with « Feuille numérique » and « Scanner une feuille ».
   #/diamond/KEY/csheets: every sheet of the Space, brick by brick (« Feuilles de concept »).
   0.60.125 (D-O-138): a sheet has its badge and its open questions (?), a drawing placed in the platform's template, and is shown
   on that template (PNG, PDF: concept_sheet_tools.js); « Feuilles de concept » creates sheets itself -- by hand for a chosen brick,
   by batch from a .zip of cards with their pictures and PDF, or with an AI, one branch of the tree at a time.
   0.60.132 (D-O-145): the AI tools of the page are one button, « ↔ IA : feuilles de concept » (concept_round.js): the prompt and
   the context .zip out, the .zip of the AI back in at once; « Importer un lot (.zip) » and « IA : une branche » are gone. */
(function () {
  "use strict";

  const { api, el, clear, field, toast, modal } = DA;
  const A = DA.agile;
  const D = DA.diamond;

  function card(ctx, s, editable, done, labels) {
    const status = (labels && labels.status ? labels.status : { open: "Open", selected: "Selected", dropped: "Dropped" })[s.status];
    const row = (label, text) => (text ? el("p", null, el("strong", null, label + " "), text) : null);
    return el("article", { class: "dm-sheet dm-sheet-" + s.kind + " dm-sheet-st-" + s.status },
      el("div", { class: "dm-cb-top" }, el("span", { class: "dm-code" }, s.code),
        el("span", { class: "badge badge-neutral" }, { digital: "Numérique", ai: "IA", scan: "Scan" }[s.kind] || s.kind),
        s.badge ? el("span", { class: "badge badge-warn" }, s.badge) : null,
        s.status !== "open" ? el("span", { class: "badge " + (s.status === "selected" ? "badge-ok" : "badge-off") }, status) : null),
      el("h3", null, s.title), ...D.sheetVisual(ctx, s),
      row("Principe :", s.principle), s.description ? el("p", { class: "dm-sheet-desc" }, s.description) : null,
      row("+", s.pros), row("−", s.cons), row("?", s.questions),
      el("p", { class: "muted dm-sheet-by" }, (s.author_name || "") + " · " + DA.formatDate(s.updated_at || s.created_at)),
      editable ? el("div", { class: "dm-actions" },
        el("button", { type: "button", class: "btn btn-small", onclick: () => openSheet(ctx, s.concept_id, s, done) }, "Modifier"),
        el("button", { type: "button", class: "btn btn-small btn-danger", onclick: async () => {
          if (!window.confirm("Archiver la feuille " + s.code + " « " + s.title + " » ?")) return;
          try { await api.post(D.base(ctx) + "/sheets/" + s.id + "/archive", {}); done(); } catch (err) { toast(err.message, "error"); }
        } }, "Archiver"),
        el("button", { type: "button", class: "btn btn-small btn-danger", "data-new": "0.60.128-sheet-delete", onclick: async () => {
          if (!window.confirm("Supprimer définitivement la feuille " + s.code + " « " + s.title + " » ? Elle ne pourra pas être récupérée "
            + "(sauf par une sauvegarde du Space). Son numéro ne sera pas redonné.")) return;
          try { await api.del(D.base(ctx) + "/sheets/" + s.id); toast(s.code + " supprimée.", "success"); done(); } catch (err) { toast(err.message, "error"); }
        } }, "Supprimer")) : null);
  }

  function sheetSection(ctx, state, editable) {
    const { concept: c, sheets } = state.data;
    return el("section", { class: "dm-cb-section", "data-new": "0.60.105-sheets" },
      el("div", { class: "dm-panel-head" }, el("h2", null, "Feuilles de concept (" + sheets.length + ")"),
        editable ? el("div", { class: "dm-actions" },
          el("button", { type: "button", class: "btn btn-small btn-primary", onclick: () => openSheet(ctx, c.id, null, state.reload) }, "Feuille numérique"),
          el("button", { type: "button", class: "btn btn-small", onclick: () => openScan(ctx, c.id, state.reload) }, "Scanner une feuille")) : null),
      c.frozen && A.canEdit(ctx) ? frozenNote(ctx, c, state.reload) : null,
      sheets.length ? el("div", { class: "dm-sheets" }, sheets.map((s) => card(ctx, s, editable, state.reload)))
        : el("p", { class: "muted" }, c.kind === "existing" ? "Concept existant : une feuille n'est utile que pour comparer des variantes."
          : "Aucune feuille. Dessinez des solutions vraiment différentes : en séance (scannez les feuilles), dans l'outil, ou avec l'IA."));
  }

  /* 0.60.125 (D-O-138): a frozen brick takes no new sheet (D-O-129) -- say so where the buttons would be, and offer « Défiger » */
  function frozenNote(ctx, c, reload) {
    const crun = async (path, body) => {
      try { await api.post(D.base(ctx) + path, body || {}); toast(c.code + " défigée : la recherche reprend.", "success"); reload(); }
      catch (err) { toast(err.message, "error"); }
    };
    return el("p", { class: "dm-frozen-note", "data-new": "0.60.125-frozen-sheets" },
      el("span", { class: "badge badge-ok" }, "Figée"), " Brique figée : pas de nouvelle feuille de concept. Défigez-la pour reprendre la recherche. ",
      el("button", { type: "button", class: "btn btn-small", onclick: () => D.unfreezeBrick(c, crun) }, "Défiger " + c.code));
  }

  /* conceptId null: the sheet's brick is chosen in the form (bricks: those that may still take a sheet) */
  function openSheet(ctx, conceptId, s, done, bricks) {
    const brick = !conceptId && bricks ? el("select", { "aria-label": "Brique" }, bricks.map((c) =>
      el("option", { value: c.id }, c.code + " " + (c.initial_name ? "« " + c.initial_name + " » " : "") + c.name))) : null;
    const title = el("input", { type: "text", maxlength: 160, value: s ? s.title : "", placeholder: "ex. Plaque froide sous les cellules" });
    const principle = el("input", { type: "text", maxlength: 600, value: s ? s.principle : "", placeholder: "Le principe en une phrase" });
    const badge = el("input", { type: "text", maxlength: 60, value: s ? s.badge || "" : "", placeholder: "ex. « sans outil » : l'atout de la feuille" });
    const description = el("textarea", { rows: 4, maxlength: 4000 }, s ? s.description : "");
    const pros = el("textarea", { rows: 3, maxlength: 1500, placeholder: "Un avantage par ligne" }, s ? s.pros : "");
    const cons = el("textarea", { rows: 3, maxlength: 1500, placeholder: "Un inconvénient par ligne" }, s ? s.cons : "");
    const questions = el("textarea", { rows: 2, maxlength: 1500, placeholder: "Une question ouverte par ligne (essai, norme, chiffre à confirmer)" }, s ? s.questions || "" : "");
    const figure = el("input", { type: "file", accept: "image/png,image/jpeg", "aria-label": "Croquis" });
    const dropFigure = s && s.figure_id ? el("input", { type: "checkbox" }) : null;
    const error = el("p", { class: "form-error", role: "alert" });
    let close = null;
    const form = el("form", { class: "ag-form", onsubmit: async (ev) => {
      ev.preventDefault();
      const body = { title: title.value, principle: principle.value, description: description.value, pros: pros.value, cons: cons.value,
        badge: badge.value, questions: questions.value };
      try {
        const cid = conceptId || (brick && Number(brick.value));
        if (!s && !cid) { error.textContent = "Choisissez la brique de la feuille."; return; }
        if (figure.files.length) body.figure_id = (await api.upload(D.base(ctx) + "/sheets/upload", figure.files[0])).id;
        else if (dropFigure && dropFigure.checked) body.figure_id = null;
        if (s) await api.patch(D.base(ctx) + "/sheets/" + s.id, body);
        else await api.post(D.base(ctx) + "/concepts/" + cid + "/sheets", Object.assign(body, { kind: "digital" }));
        close();
        done();
      } catch (err) { error.textContent = err.message; }
    } }, brick ? field("Brique technologique", brick) : null, field("Titre", title), field("Principe de fonctionnement", principle),
    el("div", { "data-new": "0.60.125-sheet-template" }, field("Badge (l'ellipse rouge du gabarit)", badge),
      field("Croquis (PNG ou JPEG), placé dans la zone de dessin du gabarit", figure),
      dropFigure ? el("label", { class: "check" }, dropFigure, "Retirer le croquis actuel") : null),
    field("Description (ce que montre la feuille : architecture, matériaux, ordres de grandeur)", description),
    el("div", { class: "dm-row" }, field("Avantages (+)", pros), field("Inconvénients (−)", cons)),
    field("Questions ouvertes (?)", questions), error,
    el("div", { class: "form-actions" }, el("button", { type: "button", class: "btn", onclick: () => close() }, "Annuler"),
      el("button", { type: "submit", class: "btn btn-primary" }, "Enregistrer")));
    close = modal(s ? "Feuille " + s.code : "Nouvelle feuille de concept", form);
    document.querySelectorAll(".modal").forEach((m) => m.classList.add("modal-wide"));
    (brick || title).focus();
  }

  function openScan(ctx, conceptId, done) {
    const file = el("input", { type: "file", accept: "image/png,image/jpeg,image/webp,application/pdf", "aria-label": "Scan" });
    const title = el("input", { type: "text", maxlength: 160, placeholder: "Titre écrit sur la feuille" });
    const principle = el("input", { type: "text", maxlength: 600, placeholder: "Le principe en une phrase (facultatif)" });
    const error = el("p", { class: "form-error", role: "alert" });
    let close = null;
    const form = el("form", { class: "ag-form", onsubmit: async (ev) => {
      ev.preventDefault();
      if (!file.files.length) { error.textContent = "Choisissez la photo ou le PDF de la feuille."; return; }
      try {
        const up = await api.upload(D.base(ctx) + "/sheets/upload", file.files[0]);
        await api.post(D.base(ctx) + "/concepts/" + conceptId + "/sheets", { title: title.value || file.files[0].name.replace(/\.[^.]+$/, ""),
          principle: principle.value, kind: "scan", attachment_id: up.id });
        close();
        done();
      } catch (err) { error.textContent = err.message; }
    } }, field("Photo ou scan (PNG, JPEG, WebP ou PDF, 15 Mo au plus)", file), field("Titre", title), field("Principe", principle), error,
    el("div", { class: "form-actions" }, el("button", { type: "button", class: "btn", onclick: () => close() }, "Annuler"),
      el("button", { type: "submit", class: "btn btn-primary" }, "Déposer")));
    close = modal("Scanner une feuille de concept", form);
  }

  /* #/diamond/KEY/csheets */
  async function listView(page, ctx) {
    const holder = el("div", { class: "dm-page" });
    page.append(holder);
    const draw = async () => {
      const [data, cdata] = await Promise.all([api.get(D.base(ctx) + "/sheets"), api.get(D.base(ctx) + "/concepts")]);
      clear(holder);
      const editable = A.canEdit(ctx);
      const open = cdata.concepts.filter((c) => !c.frozen);  // a frozen brick takes no new sheet (D-O-129)
      const reload = () => D.later(draw);
      holder.append(A.pageHead(ctx, [el("span", null, "Diamond"), el("span", null, "Feuilles de concept")],
        editable && open.length ? [
          el("button", { type: "button", class: "btn btn-small btn-primary", "data-new": "0.60.125-sheets-new",
            onclick: () => openSheet(ctx, null, null, reload, open) }, "Nouvelle feuille"),
          el("button", { type: "button", class: "btn btn-small", "data-new": "0.60.132-round",
            onclick: () => D.openConceptRound(ctx, reload) }, "↔ IA : feuilles de concept"),
          el("button", { type: "button", class: "btn btn-small", "data-new": "0.60.133-review",
            onclick: () => D.openReview(ctx, reload) }, "▶ Revue")] : null),
        el("div", { class: "page-head dm-intro" }, el("h1", { "data-new": "0.60.105-csheets" }, "Feuilles de concept"),
          el("p", { class: "muted" }, "Toutes les solutions dessinées, brique par brique, sur le gabarit de la plateforme. « ↔ IA : feuilles de concept » : choisissez "
            + "une branche ou toutes, copiez le prompt pour votre assistant IA, puis déposez le .zip qu'il rend ; recommencez à chaque tour "
            + "de créativité. « ▶ Revue » : une feuille à la fois, au clavier, pour garder, écarter ou supprimer. Elles nourrissent le "
            + "tableau morphologique et les matrices de Pugh.")));
      if (!data.sheets.length) {
        holder.append(el("div", { class: "empty" }, el("p", null, open.length
          ? "Aucune feuille pour l'instant : « Nouvelle feuille » ou « ↔ IA : feuilles de concept » (en haut)."
          : "Aucune brique où dessiner une feuille : créez d'abord les briques technologiques."),
        el("a", { class: "btn" + (open.length ? "" : " btn-primary"), href: A.href(ctx, "concepts") }, "Briques technologiques")));
        return;
      }
      // 0.60.128 (D-O-141): by branch of the tree, then by brick, each foldable (concept_sheet_fold.js)
      holder.append(D.sheetsByBranch(ctx, data, cdata, (s) => card(ctx, s, editable, reload, data.labels), editable, reload));
    };
    await draw();
  }

  D.sheetSection = sheetSection;
  D.editSheet = (ctx, s, done) => openSheet(ctx, s.concept_id, s, done);  // 0.60.133 (D-O-146): « M » in « Revue »
  A.views.csheets = listView;
})();
