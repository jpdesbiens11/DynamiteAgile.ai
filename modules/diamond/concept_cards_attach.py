"""Diamond · « Importer un lot (.zip) » onto the sheets that already exist (0.60.129, D-O-142).

A picture (PNG, JPEG) or a PDF of the .zip, without a card, whose name STARTS with the code of a sheet of the Space followed by
« _ », « - », « . » or the end of the name (CB-1.1_croquis_ia.png, CB-6.2-v2.jpg, CB-1.1.png) goes on that sheet:
  - a picture becomes its picture (attachment_id), the one a scan deposited in the page takes (the same checks: the real format read
    in the first bytes, the size); the previous picture stays in the attachments of the Space (a backup, « Changements »);
  - a PDF becomes its PDF (pdf_id) when the sheet has a picture, else its scan (attachment_id);
  - the sheet keeps its nature (an « ai » sheet stays « ai ») and its number; no sheet is created.
A range (CB-3.1-3.6_brainwriting.pdf) is the brick's, never CB-3.1's. A code of an archived or unknown sheet keeps the previous
behaviour (a new « Scan » sheet, concept_cards.py) with a warning. The card of a sheet in the .zip keeps its files.
"""
import hashlib
import json
import re

from core import audit, db, uploads
from core.errors import ApiError

from . import concept_sheets as S

LEAD = re.compile(r"^CB-(\d+)\.(\d+)(?=[_.\-]|$)", re.I)
RANGE_LEAD = re.compile(r"^CB-\d+\.\d+-\d+(?:\.\d+)?(?=[_.\-]|$)", re.I)
PDF = "application/pdf"


def lead_code(name):
    """CB-n.m when the file name starts with it (not a range), else None."""
    if RANGE_LEAD.match(name):
        return None
    m = LEAD.match(name)
    return "CB-{}.{}".format(int(m.group(1)), int(m.group(2))) if m else None


def check(name, data, mime):
    """Why this file would be refused by the route of a scan (its first bytes), or None."""
    if mime == PDF:
        return None if data.startswith(b"%PDF-") else "« {} » n'est pas un vrai PDF (lu dans les premiers octets)".format(name)
    found = uploads.sniff_image(data)
    if found is None:
        return "« {} » n'est pas une vraie image PNG ou JPEG (lu dans les premiers octets)".format(name)
    return None


def unreadable(names, files):
    """The first refusal among the files of a new sheet, or None."""
    for n in names:
        why = check(n, *files[n])
        if why:
            return why
    return None


def _sheets(conn, pid):
    """{code: sheet} of the active sheets, {code: True} of the archived ones (the brick active or not)."""
    active = {s["code"]: s for s in S.rows(conn, pid)}
    archived = {}
    for r in conn.execute("SELECT s.number, c.number AS cn FROM diamond_concept_sheets s JOIN diamond_concepts c ON c.id = s.concept_id "
                          "WHERE s.project_id = ? AND (s.archived = 1 OR c.archived = 1)", (pid,)):
        archived[S.code(r["cn"], r["number"])] = True
    return active, archived


def _sha(conn, aid):
    row = conn.execute("SELECT sha256 FROM attachments WHERE id = ?", (aid,)).fetchone() if aid else None
    return row["sha256"] if row else None


def plan(conn, pid, files, used):
    """The lines « file → existing sheet », and {code: warning} of the codes with no active sheet. Adds the files taken to `used`."""
    active, archived = _sheets(conn, pid)
    frozen = {r["id"] for r in conn.execute("SELECT id FROM diamond_concepts WHERE project_id = ? AND frozen = 1", (pid,))}
    entries, warnings, picked = [], {}, {}
    with_picture = {lead_code(n) for n in files if n not in used and files[n][1] != PDF}
    for name in sorted(files):
        code = lead_code(name) if name not in used else None
        if code is None:
            continue
        sheet = active.get(code)
        if sheet is None:
            warnings[code] = ("{} est archivée : « {} » devient une nouvelle feuille Scan".format(code, name) if code in archived
                              else "aucune feuille {} dans ce Space : « {} » devient une nouvelle feuille Scan".format(code, name))
            continue
        used.add(name)
        data, mime = files[name]
        image = mime != PDF
        e = {"key": "file:" + name, "code": code, "title": sheet["title"], "files": [name], "kind": sheet["kind"],
             "brick": "CB-{}".format(sheet["concept_number"]), "sheet_id": sheet["id"],
             "action": "image" if image else "pdf"}
        has_picture = bool(sheet["attachment_id"]) and str(sheet.get("file_mime") or "").startswith("image/")
        slot = "attachment_id" if image or not (has_picture or code in with_picture) else "pdf_id"
        e["slot"] = slot
        e["replaces"] = bool(sheet[slot])
        why = check(name, data, mime)
        if why:
            e.update(status="refused", reason=why)
        elif sheet["concept_id"] in frozen:
            e.update(status="refused", reason="{} est figée".format(e["brick"]))
        elif (code, "image" if image else "pdf") in picked:
            e.update(status="refused", reason="un seul fichier de ce type par feuille : « {} » est déjà retenu"
                     .format(picked[(code, "image" if image else "pdf")]))
        elif _sha(conn, sheet[slot]) == hashlib.sha256(data).hexdigest():
            e.update(status="exists", reason="ce fichier est déjà celui de " + code)
        else:
            e.update(status="attach")
            picked[(code, "image" if image else "pdf")] = name
        entries.append(e)
    return entries, warnings


def skip_keys(raw):
    """The keys of the unticked lines (?skip=<JSON list>)."""
    if not raw:
        return set()
    try:
        keys = json.loads(raw)
    except ValueError:
        raise ApiError(400, "Paramètre skip illisible : une liste JSON des lignes décochées est attendue.")
    if not isinstance(keys, list):
        raise ApiError(400, "Paramètre skip : une liste JSON des lignes décochées est attendue.")
    return {str(k) for k in keys[:2000]}


def apply(ctx, pid, entries, files, store):
    """Stores each file (the checks of a scan) and puts it on its sheet; returns the codes changed."""
    done = []
    for e in entries:
        name = e["files"][0]
        aid = store(ctx, pid, name, *files[name])
        sheet = ctx.conn.execute("SELECT * FROM diamond_concept_sheets WHERE id = ?", (e["sheet_id"],)).fetchone()
        sets = {e["slot"]: aid}
        old = sheet[e["slot"]]
        if e["slot"] == "attachment_id" and old and not sheet["pdf_id"]:  # a scan PDF replaced by a picture stays as its PDF
            row = ctx.conn.execute("SELECT mime FROM attachments WHERE id = ?", (old,)).fetchone()
            if row is not None and row["mime"] == PDF and e["action"] == "image":
                sets["pdf_id"] = old
        cols = ", ".join("{} = ?".format(k) for k in sets)
        ctx.conn.execute("UPDATE diamond_concept_sheets SET {}, updated_by = ?, updated_at = ? WHERE id = ?".format(cols),
                         tuple(sets.values()) + (ctx.user["id"], db.utc_now(), e["sheet_id"]))
        audit.log_action(ctx.conn, ctx.user["id"], "diamond_sheet_attach", "diamond_concept_sheet", e["sheet_id"],
                         {"code": e["code"], "file": name, "slot": e["slot"], "attachment": aid, "previous": old}, ctx.ip)
        done.append(e["code"])
    return done
