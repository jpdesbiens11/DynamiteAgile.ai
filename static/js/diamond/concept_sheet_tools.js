/* Diamond · concept sheets, the sheet on its template (0.60.125, D-O-138): the server draws it (/sheets/<id>/sheet.svg and .pdf);
   « PNG » turns the SVG into a picture in the browser (a canvas: nothing leaves the page). 0.60.129 (D-O-142): a sheet with its own
   picture is shown and exported (PNG, PDF) as that picture. 0.60.132 (D-O-145): « Importer un lot (.zip) » and « IA : une branche »
   left this file for the one AI tool of the page, « ↔ IA : feuilles de concept » (concept_round.js). */
(function () {
  "use strict";

  const { el, toast } = DA;
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

  /* The picture of a sheet in its card: the deposited picture, else the sheet drawn on the template; and its files.
     opts.thumb (0.60.136, D-O-149): a thumbnail, not a link -- a double-click on the card shows the sheet in detail. */
  function visual(ctx, s, opts) {
    const picture = s.attachment_id && String(s.file_mime || "").startsWith("image/");
    const src = picture ? fileUrl(ctx, s) : sheetUrl(ctx, s, "svg") + "?v=" + encodeURIComponent(s.updated_at || "");
    const img = el("img", { class: "dm-sheet-scan", src, alt: "Feuille " + s.code, loading: "lazy" });
    const thumb = s.attachment_id && !picture ? null : opts && opts.thumb ? el("div", { class: "dm-sheet-visual dm-sheet-thumb" }, img)
      : el("a", { href: src, target: "_blank", rel: "noopener", class: "dm-sheet-visual" }, img);
    const links = el("div", { class: "dm-actions dm-sheet-files", "data-new": "0.60.125-sheet-files" },
      s.attachment_id && !picture ? el("a", { class: "btn btn-small", href: fileUrl(ctx, s), target: "_blank", rel: "noopener" }, "Ouvrir le scan (PDF)") : null,
      s.pdf_id ? el("a", { class: "btn btn-small", href: fileUrl(ctx, s, "pdf"), target: "_blank", rel: "noopener" }, picture ? "PDF joint" : "PDF") : null,
      !s.attachment_id || picture ? el("button", { type: "button", class: "btn btn-small", "data-new": picture ? "0.60.129-sheet-image-export" : null,
        "data-tip": picture ? "L'image de la feuille" : "La feuille au gabarit, en image", onclick: () => savePng(ctx, s, picture) }, "PNG") : null,
      !s.attachment_id || picture ? el("a", { class: "btn btn-small", href: sheetUrl(ctx, s, "pdf"),
        "data-tip": picture ? "L'image de la feuille, A4 paysage" : "La feuille au gabarit, A4 paysage" }, "PDF") : null);
    return [thumb, links];
  }

  Object.assign(D, { sheetVisual: visual });
})();
