"""Diamond · the technology bricks and the competencies in the exports of the functional tree (0.60.126, D-O-139).

The screen « Arbre fonctionnel » shows, after the deepest column of functions, the column « Concept initial / Brique
technologique » and, when the part is on, the grid of the competencies. Its export (« Exporter ▾ ») now carries them too:
  Excel       a « Brique » column on each function, the sheet « Briques technologiques » (one line per brick), and the two
              sheets of « Compétences et équipe »;
  draw.io     the column of the bricks, each linked to its functions, with the competencies of its lines (drawio_bricks);
  PowerPoint  the same pages (export_pptx.py draws the draw.io pages), so does the figure of the Word report.
"""
from . import concepts as C

KIND_FILL = {"existing": "#DFF3E4", "to_define": "#FFF1C7"}
FROZEN_FILL = "#E3E8F0"


def gather(conn, pid):
    """The bricks of the Space (concepts.rows) and the brick of each function."""
    bricks = C.rows(conn, pid)
    of = {fid: c for c in bricks for fid in c["function_ids"]}
    return {"concepts": bricks, "brick_of": of, "concept_labels": {"kinds": C.KINDS, "status": C.STATUS}}


def brick_cell(c):
    if not c:
        return ""
    return c["code"] + (" « {} »".format(c["initial_name"]) if c.get("initial_name") else " " + c["name"])


def competencies_of(data):
    """{brick id: {code: highest rating of its lines}} -- what each brick asks of the team."""
    comp = data.get("competencies")
    out = {}
    for ln in (comp or {}).get("lines", []):
        mine = out.setdefault(ln["brick"]["id"], {})
        for code, rating in ln["ratings"].items():
            if rating:
                mine[code] = max(mine.get(code, 0), rating)
    return out


def landed(c):
    if c.get("frozen"):
        return "Figée : " + (c.get("frozen_text") or "")
    if c.get("selected_sheet"):
        return "Retenu : {} {}".format(c["selected_sheet"]["code"], c["selected_sheet"]["title"])
    return ""


# ---------------------------------------------------------------- Excel
def bricks_sheet(book, kit, data):
    from .export_xlsx import _frame, _table
    s = book.sheet("Briques technologiques")
    widths = [8, 26, 34, 16, 12, 18, 30, 30, 20, 9, 40, 24]
    _frame(s, data, "Briques technologiques — Concept initial / Brique", widths, kit, "E0602F")
    lab = data["concept_labels"]
    code = {f["id"]: "F{}".format(f["number"]) for f in data["tree"]}
    comp = competencies_of(data)
    rows = [[c["code"], c.get("initial_name") or "", c["name"], lab["kinds"].get(c["kind"], c["kind"]),
             lab["status"].get(c["status"], c["status"]), c.get("owner_name") or "", c.get("branch_lead") or "", c.get("reference") or "",
             ", ".join(code[i] for i in c["function_ids"] if i in code), c.get("sheets") or 0, landed(c),
             " · ".join("{} {}".format(k, v) for k, v in sorted(comp.get(c["id"], {}).items()))] for c in data["concepts"]]
    _table(s, kit, ["Code", "Concept initial", "Brique technologique", "Nature", "Status", "Responsable", "Responsable de la branche", "Référence", "Fonctions",
                    "Feuilles", "Concept retenu", "Compétences (note max.)"],
           rows or [["—"] + [""] * 11], widths, (lambda v: [kit.wrap] * 12) if rows else None)


# ---------------------------------------------------------------- draw.io / PowerPoint
def drawio_bricks(page, data, ids, ypos, x, h, h_func, w, head, esc):
    """The column of the bricks at x: each brick in the middle of its functions (pushed down so that none overlaps), one
    bracket line per function. ids / ypos: the boxes of the functions drawn on this page. Returns the legend items."""
    comp = competencies_of(data)
    lab = data["concept_labels"]["kinds"]
    placed = []
    for c in data["concepts"]:
        ys = [ypos[i] for i in c["function_ids"] if i in ids]
        if ys:
            placed.append((min(ys) + max(ys) + h_func - h) / 2)
            placed[-1] = (placed[-1], c)
    placed.sort(key=lambda p: p[0])
    floor = head
    drawn = False
    for want, c in placed:
        y = max(want, floor)
        floor = y + h + 12
        lines = ["<b>{}</b> {}".format(esc(c["code"]), esc(lab.get(c["kind"], "")) if not c.get("frozen") else "Figée")]
        lines.append("<b>« {} »</b>".format(esc(c["initial_name"])) if c.get("initial_name") else "<b>{}</b>".format(esc(c["name"])))
        if c.get("initial_name"):
            lines.append(esc(c["name"]))
        tail = landed(c)
        if tail:
            lines.append('<i>{}</i>'.format(esc(tail[:90])))
        skills = comp.get(c["id"])
        if skills:
            lines.append('<font style="font-size:10px" color="#0E7490">{}</font>'.format(
                esc(" · ".join("{} {}".format(k, v) for k, v in sorted(skills.items())))))
        fill = FROZEN_FILL if c.get("frozen") else KIND_FILL.get(c["kind"], "#FFFFFF")
        bid = page.box(x, y, w, h, "<br>".join(lines), "rounded=1;arcSize=10;fillColor={};strokeColor=#E0602F;strokeWidth=1.6;"
                       "fontSize=11;fontColor=#1F2933;align=left;spacingLeft=8;".format(fill))
        for fid in c["function_ids"]:
            if fid in ids:
                page.edge(ids[fid], bid, "edgeStyle=elbowEdgeStyle;elbow=horizontal;rounded=1;endArrow=none;dashed=1;"
                          "strokeColor=#E0602F;strokeWidth=1.2;")
        drawn = True
    if not drawn:
        return []
    return [("rounded=1;fillColor={};strokeColor=#E0602F;".format(KIND_FILL["existing"]), "Brique : concept existant"),
            ("rounded=1;fillColor={};strokeColor=#E0602F;".format(KIND_FILL["to_define"]), "Brique : à définir"),
            ("rounded=1;fillColor={};strokeColor=#E0602F;".format(FROZEN_FILL), "Brique figée (concept retenu)"),
            ("text;fontSize=10;fontColor=#0E7490;strokeColor=none;fillColor=none;", "Compétences : note max. des lignes (1 à 5)")]
