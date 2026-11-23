"""Diamond · a concept sheet on the platform's template, as a file (0.60.125, D-O-138).

    GET /sheets/<sid>/sheet.svg   the sheet drawn on the template (shown in the page; the browser turns it into a PNG)
    GET /sheets/<sid>/sheet.pdf   the same sheet, vector, A4 landscape (an export: stamped and registered, D-B-129)

concept_sheet_render.py draws it; the drawing in the template is the sheet's figure (figure_id), else its text.
"""
import re

from core import permissions, prefs, uploads, validate
from core.errors import ApiError
from core.files import RawFile

from . import concept_sheet_render as R
from . import concept_sheets as S


def _sheet(ctx):
    pid = validate.int_param(ctx.params, "pid")
    permissions.require_project_role(ctx.conn, ctx.user, pid, "reader")
    sid = validate.int_param(ctx.params, "sid")
    s = next((x for x in S.rows(ctx.conn, pid) if x["id"] == sid), None)
    if s is None:
        raise ApiError(404, "Feuille de concept introuvable dans ce Space. Correctif : rechargez la page.")
    s["figure"] = None
    if s.get("figure_id"):
        row = ctx.conn.execute("SELECT * FROM attachments WHERE id = ? AND project_id = ?", (s["figure_id"], pid)).fetchone()
        if row is not None and row["mime"] in ("image/png", "image/jpeg"):
            s["figure"] = (uploads.read(ctx.data_dir, row), row["mime"])
    author = ""
    if s.get("author_id"):
        author = prefs.get(ctx.conn, s["author_id"]).get("initials") or s.get("author_name") or ""
    space = ctx.conn.execute("SELECT name FROM projects WHERE id = ?", (pid,)).fetchone()["name"]
    meta = {"author": author, "date": (s.get("updated_at") or s.get("created_at") or "")[:10], "space": space,
            "source": S.KINDS.get(s["kind"], "")}
    return s, meta


def _name(s, ext):
    slug = re.sub(r"[^\w]+", "_", s["title"].lower()).strip("_")[:50]
    return "{}_{}.{}".format(s["code"], slug, ext)


def api_svg(ctx):
    s, meta = _sheet(ctx)
    return RawFile(R.svg(R.layout(s, meta)), _name(s, "svg"), "image/svg+xml", inline=True, export=False)


def api_pdf(ctx):
    s, meta = _sheet(ctx)
    return RawFile(R.pdf(R.layout(s, meta)), _name(s, "pdf"), "application/pdf")
