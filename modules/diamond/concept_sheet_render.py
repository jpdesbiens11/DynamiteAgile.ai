"""Diamond · a concept sheet drawn on the platform's template (0.60.125, D-O-138), standard library only.

The template of the paper sheets of a creativity session, the one the team liked: a page of a notebook (cream paper, ruled
lines, the red margin), a dark frame, the title in hand writing underlined with a yellow highlighter, a red ellipse with the
one-line « badge » (« sans outil »), the drawing on the left, the + (green), − (red) and ? (blue) on the right, and the
title block at the bottom right: « Concept sheet CB-3.2 », the brick, the author and the date, the Space and the source.

One layout (layout(), in pixels of an A4 landscape page at 96 dpi), two outputs:
  svg(items)  the sheet in the page and as a PNG (the browser draws the SVG on a canvas);
  pdf(items)  the same sheet, vector, A4 landscape (Helvetica Oblique: no font is embedded).
The drawing is the sheet's figure (a PNG or JPEG attached to it); without one, the principle and the description are written in
the drawing area, as on a sheet that has not been sketched yet.
"""
import base64
import zlib
from xml.sax.saxutils import escape

from modules.dynamite.export_pdf import jpeg_info, pdf_string, png_to_rgb, width

W, H = 1123, 794  # A4 landscape, px at 96 dpi
PAPER, RULE, MARGIN_RED, INK = "#f9f7f1", "#dfe3ea", "#f0a5a5", "#1f2430"
GREEN, RED, BLUE, GRAY, HIGHLIGHT = "#2e8b3a", "#c9302c", "#2f5fd0", "#8a8f99", "#f5d55b"
HAND = "'Ink Free','Segoe Print','Bradley Hand','Noteworthy','Comic Sans MS','Comic Neue',sans-serif"  # system fonts only (no font is loaded)
SCALE = 1.08  # a handwritten font is a little wider than Helvetica: the wrap stays inside the template


def _wrap(text, size, max_w):
    lines = []
    for para in str(text or "").splitlines():
        words, cur = para.split(), ""
        for w in words:
            probe = (cur + " " + w).strip()
            if cur and width(probe, "I", size) * SCALE > max_w:
                lines.append(cur)
                cur = w
            else:
                cur = probe
        if cur:
            lines.append(cur)
    return lines


def _items(text):
    """The lines of a list field (« + … », one per line); the leading sign is dropped, the template draws its own."""
    out = []
    for line in str(text or "").splitlines():
        line = line.strip().lstrip("+−-–?•*").strip()
        if line:
            out.append(line)
    return out


def layout(sheet, meta):
    """sheet: the row of concept_sheets.rows (+ figure: (bytes, mime) or None); meta: {space, author, date, source}."""
    it = [("rect", 0, 0, W, H, PAPER, None, 0)]
    for y in range(36, H, 24):
        it.append(("line", 0, y, W, y, RULE, 1))
    it.append(("line", 69, 0, 69, H, MARGIN_RED, 1.2))
    it.append(("rect", 24, 24, W - 48, H - 48, None, INK, 2.2))
    title = sheet["title"]
    t_lines = _wrap(title, 25, 900)[:2]
    hl = min(max(width(t_lines[0], "I", 25) * SCALE + 40, 200), 1000) if t_lines else 200
    it.append(("rect", 45, 70 + 30 * (len(t_lines) - 1), hl, 8, HIGHLIGHT, None, 0, 4))
    for i, line in enumerate(t_lines):
        it.append(("text", 54, 64 + 30 * i, line, 25, INK, True, "start"))
    if sheet.get("badge"):
        badge = sheet["badge"][:40]
        rx = max(60, min(140, width(badge, "I", 16) * SCALE / 2 + 26))
        cx = min(990, 1080 - rx)
        it.append(("ellipse", cx, 132, rx, 24, RED, 1.8))
        it.append(("text", cx, 138, badge, 16, RED, False, "middle"))
    # the right column: + / − / ?
    y = 196
    for sign, color, text in (("+", GREEN, sheet.get("pros")), ("−", RED, sheet.get("cons")), ("?", BLUE, sheet.get("questions"))):
        entries = _items(text)
        for entry in entries:
            for k, line in enumerate(_wrap(sign + " " + entry, 15, 330)):
                if y > 600:
                    break
                it.append(("text", 750 + (0 if k == 0 else 12), y, line, 15, color, False, "start"))
                y += 24
        if entries:
            y += 14
    # the drawing area
    box = (93, 112, 534, 410)
    fig = sheet.get("figure")
    if fig:
        info = _image_size(*fig)
        if info:
            iw, ih = info
            k = min(box[2] / iw, box[3] / ih)
            dw, dh = iw * k, ih * k
            it.append(("image", box[0] + (box[2] - dw) / 2, box[1] + (box[3] - dh) / 2, dw, dh, fig[0], fig[1]))
        y = 556
        for line in _wrap(sheet.get("principle"), 13, 600)[:2]:
            it.append(("text", 94, y, line, 13, GRAY, False, "start"))
            y += 22
        for line in _wrap(sheet.get("description"), 13, 600)[:3]:
            it.append(("text", 106, y, line, 13, INK, False, "start"))
            y += 22
    else:
        y = 150
        for line in _wrap(sheet.get("principle"), 18, 560)[:5]:
            it.append(("text", 94, y, line, 18, INK, False, "start"))
            y += 28
        y += 14
        for line in _wrap(sheet.get("description"), 14, 590)[:15]:
            if y > 620:
                it.append(("text", 94, y, "…", 14, GRAY, False, "start"))
                break
            it.append(("text", 94, y, line, 14, "#3b4252", False, "start"))
            y += 24
    # the title block
    x0, y0, x1, y1 = 718, 642, 1094, 765
    it.append(("rect", x0, y0, x1 - x0, y1 - y0, PAPER, INK, 2.4))
    for yy in (674, 705, 736):
        it.append(("line", x0, yy, x1, yy, INK, 1.6))
    it.append(("text", x0 + 12, 667, "Concept sheet " + sheet["code"], 19, INK, True, "start"))
    brick = "Brique : CB-{} {}".format(sheet["concept_number"], sheet.get("concept_name") or "")
    it.append(("text", x0 + 12, 696, _fit(brick, 13, x1 - x0 - 24), 13, INK, False, "start"))
    it.append(("text", x0 + 12, 727, _fit("Auteur : " + (meta.get("author") or "—"), 13, 220), 13, BLUE, False, "start"))
    it.append(("text", x1 - 14, 727, meta.get("date") or "", 13, INK, False, "end"))
    it.append(("text", x0 + 12, 757, _fit(" · ".join(p for p in (meta.get("space"), meta.get("source")) if p), 12, x1 - x0 - 24),
               12, GRAY, False, "start"))
    return it


def picture(data, mime):
    """0.60.129 (D-O-142): the page of a sheet that has its own picture -- that picture, centred on A4 landscape -- or None when
    the PDF cannot hold it (a CMYK JPEG, an interlaced PNG: the template is drawn instead)."""
    size = _image_size(data, mime)
    if not size or not size[0] or not size[1]:
        return None
    if mime == "image/jpeg":
        j = jpeg_info(data)
        if not j or j[2] not in (1, 3):
            return None
    elif not png_to_rgb(data, [8_000_000]):
        return None
    pad = 24
    k = min((W - 2 * pad) / size[0], (H - 2 * pad) / size[1])
    dw, dh = size[0] * k, size[1] * k
    return [("rect", 0, 0, W, H, "#ffffff", None, 0), ("image", (W - dw) / 2, (H - dh) / 2, dw, dh, data, mime)]


def _fit(text, size, max_w):
    text = str(text or "")
    while text and width(text, "I", size) * SCALE > max_w:
        text = text[:-2] + "…" if len(text) > 2 else ""
    return text


def _image_size(data, mime):
    if mime == "image/png" and data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if mime == "image/jpeg":
        j = jpeg_info(data)
        return (j[0], j[1]) if j else None
    return None


# ---------------------------------------------------------------- SVG
def svg(items):
    out = ['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{0}" height="{1}" '
           'viewBox="0 0 {0} {1}" font-family="{2}">'.format(W, H, escape(HAND, {'"': "&quot;"}))]
    for i in items:
        kind = i[0]
        if kind == "rect":
            rx = ' rx="{}"'.format(i[8]) if len(i) > 8 else ""
            out.append('<rect x="{:.1f}" y="{:.1f}" width="{:.1f}" height="{:.1f}" fill="{}" stroke="{}" stroke-width="{}"{}/>'.format(
                i[1], i[2], i[3], i[4], i[5] or "none", i[6] or "none", i[7], rx))
        elif kind == "line":
            out.append('<line x1="{:.1f}" y1="{:.1f}" x2="{:.1f}" y2="{:.1f}" stroke="{}" stroke-width="{}"/>'.format(*i[1:7]))
        elif kind == "ellipse":
            out.append('<ellipse cx="{:.1f}" cy="{:.1f}" rx="{:.1f}" ry="{:.1f}" fill="none" stroke="{}" stroke-width="{}" '
                       'transform="rotate(-2 {:.1f} {:.1f})"/>'.format(i[1], i[2], i[3], i[4], i[5], i[6], i[1], i[2]))
        elif kind == "text":
            out.append('<text x="{:.1f}" y="{:.1f}" font-size="{}" fill="{}"{}{}>{}</text>'.format(
                i[1], i[2], i[4], i[5], ' font-weight="700"' if i[6] else "",
                ' text-anchor="{}"'.format(i[7]) if i[7] != "start" else "", escape(i[3])))
        elif kind == "image":
            href = "data:{};base64,{}".format(i[6], base64.b64encode(i[5]).decode("ascii"))
            out.append('<image x="{:.1f}" y="{:.1f}" width="{:.1f}" height="{:.1f}" href="{}" xlink:href="{}"/>'.format(
                i[1], i[2], i[3], i[4], href, href))
    out.append("</svg>")
    return "\n".join(out).encode("utf-8")


# ---------------------------------------------------------------- PDF (A4 landscape, points)
PW, PH = 842, 595
K = PW / W  # px → pt


def _rgb(hexa):
    return tuple(int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5))


PDF_TEXT = {"−": "–", "Δ": "Delta ", "δ": "delta ", "τ": "tau ", "η": "eta ", "λ": "lambda ", "₂": "2", "₃": "3", "²": "²", "³": "³"}


def _winansi(text):
    """The standard fonts of a PDF are WinAnsi: the minus sign and a few Greek letters are written out instead of « ? »."""
    return "".join(PDF_TEXT.get(ch, ch) for ch in text)


def pdf(items):
    ops, images = [], []
    for i in items:
        kind = i[0]
        if kind == "rect":
            x, y, w, h = i[1] * K, PH - (i[2] + i[4]) * K, i[3] * K, i[4] * K
            if i[5]:
                ops.append(b"%.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f" % (*_rgb(i[5]), x, y, w, h))
            if i[6]:
                ops.append(b"%.3f %.3f %.3f RG %.2f w %.2f %.2f %.2f %.2f re S" % (*_rgb(i[6]), i[7] * K, x, y, w, h))
        elif kind == "line":
            ops.append(b"%.3f %.3f %.3f RG %.2f w %.2f %.2f m %.2f %.2f l S" % (
                *_rgb(i[5]), i[6] * K, i[1] * K, PH - i[2] * K, i[3] * K, PH - i[4] * K))
        elif kind == "ellipse":
            cx, cy, rx, ry, c = i[1] * K, PH - i[2] * K, i[3] * K, i[4] * K, 0.5523
            ops.append(b"%.3f %.3f %.3f RG %.2f w %.2f %.2f m " % (*_rgb(i[5]), i[6] * K, cx + rx, cy)
                       + b"%.2f %.2f %.2f %.2f %.2f %.2f c " % (cx + rx, cy + c * ry, cx + c * rx, cy + ry, cx, cy + ry)
                       + b"%.2f %.2f %.2f %.2f %.2f %.2f c " % (cx - c * rx, cy + ry, cx - rx, cy + c * ry, cx - rx, cy)
                       + b"%.2f %.2f %.2f %.2f %.2f %.2f c " % (cx - rx, cy - c * ry, cx - c * rx, cy - ry, cx, cy - ry)
                       + b"%.2f %.2f %.2f %.2f %.2f %.2f c S" % (cx + c * rx, cy - ry, cx + rx, cy - c * ry, cx + rx, cy))
        elif kind == "text":
            size = i[4] * K
            font = "BI" if i[6] else "I"
            x = i[1] * K
            if i[7] != "start":
                tw = width(i[3], font, size)
                x -= tw if i[7] == "end" else tw / 2
            ops.append(b"BT %.3f %.3f %.3f rg /F%s %.2f Tf %.2f %.2f Td " % (*_rgb(i[5]), font.encode(), size, x, PH - i[2] * K)
                       + pdf_string(_winansi(i[3])) + b" Tj ET")
        elif kind == "image":
            info = None
            if i[6] == "image/jpeg":
                j = jpeg_info(i[5])
                if j and j[2] in (1, 3):
                    info = (j[0], j[1], j[2], i[5], "DCTDecode")
            else:
                p = png_to_rgb(i[5], [8_000_000])
                if p:
                    info = (p[0], p[1], p[2], zlib.compress(p[3], 6), "FlateDecode")
            if info:
                name = b"Im%d" % (len(images) + 1)
                images.append((name, info))
                ops.append(b"q %.2f 0 0 %.2f %.2f %.2f cm /%s Do Q" % (i[3] * K, i[4] * K, i[1] * K, PH - (i[2] + i[4]) * K, name))
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>", None]
    fonts = []
    for key, name in (("I", b"Helvetica-Oblique"), ("BI", b"Helvetica-BoldOblique")):
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>" % name)
        fonts.append(b"/F%s %d 0 R" % (key.encode(), len(objects)))
    xobj = []
    for name, (w, h, colors, stream, flt) in images:
        space = b"/DeviceRGB" if colors == 3 else b"/DeviceGray"
        objects.append(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s /BitsPerComponent 8 /Filter /%s "
                       b"/Length %d >>\nstream\n" % (w, h, space, flt.encode(), len(stream)) + stream + b"\nendstream")
        xobj.append(b"/%s %d 0 R" % (name, len(objects)))
    content = zlib.compress(b"\n".join(ops))
    objects.append(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(content) + content + b"\nendstream")
    objects[2] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /Font << %s >> /XObject << %s >> >> "
                  b"/Contents %d 0 R >>" % (PW, PH, b" ".join(fonts), b" ".join(xobj), len(objects)))
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)
