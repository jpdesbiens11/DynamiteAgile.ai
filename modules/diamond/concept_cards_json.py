"""Diamond · « Importer un lot (.zip) » with the AI's answer inside (0.60.131, D-O-144).

The .zip may hold a reponse.json (any .json) of the form the « ↔ IA » prompts give, plus the sketch of each sheet:
    {"sheets": [{"code": "CB-6.6", "concept": "CB-6", "kind": "ai", "status": "open", "title": "…", "principle": "…",
                 "description": "…", "pros": "…" | [...], "cons": "…" | [...], "questions": "…" | [...], "badge": "…",
                 "image": "images/CB-6.6_schema.png", "pdf": "…"}]}
`code` (CB-n.m) or `concept` (CB-n) names the brick; `questions` and `badge` are optional (older answers have neither).
Each sheet of the answer is a card like a .md card, with three differences:
  - a code that already names an active sheet of the Space UPDATES that sheet (its text, its sketch), never a duplicate;
    nothing changes → « Déjà là »;
  - a new code creates the sheet with that number (kind « ai » unless the answer says otherwise, its status), whatever its title:
    two sheets « Schema » under CB-6.6 and CB-6.7 are two sheets;
  - its picture is the sheet's figure (figure_id): the sheet is drawn on the platform's template (title, badge, + / − / ?,
    title block), as a sheet made through « ↔ IA ». A picture the sheet had as its own (attachment_id) steps aside for the
    template; it stays in the attachments of the Space (and becomes the figure when the answer brings none). A Scan sheet that
    the answer calls « ai » becomes « ai » again (a sheet the earlier import turned into a Scan by mistake is repaired).
Every sheet of the answer gets a line in the report; a file it names is never turned into a Scan sheet.
"""
import hashlib
import json
import re

from core import audit, db

from . import concept_sheets as S

CODE = re.compile(r"^\s*CB-(\d+)\.(\d+)\s*$", re.I)
BRICK = re.compile(r"^\s*CB-(\d+)\s*$", re.I)
TEXT = ("title", "principle", "description", "pros", "cons", "questions", "badge")
NEW_STATUS = ("open", "dropped")  # « selected » comes from a Pugh matrix only
PDF = "application/pdf"
DRAWABLE = ("image/png", "image/jpeg")  # what the template draws


def code_key(code):
    """CB-6.10 after CB-6.9 (numbers, not strings); a missing code last."""
    m = re.match(r"CB-(\d+)(?:\.(\d+))?", str(code or ""), re.I)
    return (0, int(m.group(1)), int(m.group(2) or 0)) if m else (1, 0, 0)


def _text(value):
    if isinstance(value, (list, tuple)):
        return "\n".join(str(v).strip() for v in value if str(v).strip())
    return "" if value is None else str(value).strip()


def _base(path):
    return str(path or "").replace("\\", "/").rsplit("/", 1)[-1]


def read(name, body):
    """(cards, warnings) of a .json in the .zip."""
    try:
        raw = json.loads(body.decode("utf-8-sig", "replace"))
    except ValueError as err:
        return [], ["« {} » illisible ({}) : aucune feuille lue dans ce fichier.".format(name, str(err)[:60])]
    if not isinstance(raw, dict) or not isinstance(raw.get("sheets"), list):
        return [], ["« {} » ignoré : un objet {{\"sheets\": […]}} est attendu (les briques s'importent par « Importer la réponse "
                    "de l'IA »).".format(name)]
    warnings = []
    if raw.get("concepts"):
        warnings.append("« {} » : les briques (« concepts ») ne sont pas créées ici ; elles s'importent par « Importer la réponse "
                        "de l'IA ».".format(name))
    if not raw["sheets"]:
        warnings.append("« {} » : aucune feuille dans « sheets ».".format(name))
    cards = []
    for i, item in enumerate(raw["sheets"]):
        where = "{} · sheets[{}]".format(name, i)
        if not isinstance(item, dict):
            warnings.append(where + " ignoré : un objet est attendu.")
            continue
        card = {k: _text(item.get(k)) for k in TEXT}
        card.update(source="json", where=where, code=None, brick=None, number=None, error=None,
                    kind=_text(item.get("kind")).lower() or "ai", status=_text(item.get("status")).lower() or None,
                    image=_base(item.get("image") or item.get("figure") or item.get("file")), pdf=_base(item.get("pdf")))
        m, b = CODE.match(_text(item.get("code"))), BRICK.match(_text(item.get("concept")))
        if m:
            card.update(code="CB-{}.{}".format(int(m.group(1)), int(m.group(2))), brick=int(m.group(1)), number=int(m.group(2)))
            if b and int(b.group(1)) != card["brick"]:
                card["error"] = "code {} et concept {} ne désignent pas la même brique".format(card["code"], _text(item.get("concept")))
        elif _text(item.get("code")):
            card["error"] = "code « {} » illisible : CB-n.m attendu".format(_text(item.get("code"))[:20])
        elif b:
            card["brick"] = int(b.group(1))
        if not card["title"] and not card["error"]:
            card["error"] = "titre manquant"
        if card["kind"] not in S.KINDS and not card["error"]:
            card["error"] = "kind « {} » inconnu ({})".format(card["kind"][:20], ", ".join(S.KINDS))
        if card["status"] and card["status"] not in NEW_STATUS:
            warnings.append("{} : status « {} » laissé de côté (open ou dropped ; « selected » vient d'une matrice de Pugh)."
                            .format(where, card["status"][:20]))
            card["status"] = None
        cards.append(card)
    return cards, warnings


def files_of(card, names, files):
    """The files of a card of the answer: the ones named by its code, plus `image` / `pdf` when the answer names them."""
    out = list(names)
    for ref in (card.get("image"), card.get("pdf")):
        if ref and ref in files and ref not in out:
            out.append(ref)
    return out


def missing(card, files):
    refs = [r for r in (card.get("image"), card.get("pdf")) if r]
    return [r for r in refs if r not in files]


def split(names, files):
    pics = [n for n in names if files[n][1] != PDF]
    pdfs = [n for n in names if files[n][1] == PDF]
    return (pics[0] if pics else None), (pdfs[0] if pdfs else None)


def _sha(conn, aid):
    row = conn.execute("SELECT sha256 FROM attachments WHERE id = ?", (aid,)).fetchone() if aid else None
    return row["sha256"] if row else None


def update_entry(conn, card, sheet, names, files):
    """The line « this sheet of the answer → the existing sheet »: what would change, or « exists »."""
    e = {"code": card["code"], "title": card["title"], "files": names, "kind": sheet["kind"], "card": card, "sheet_id": sheet["id"],
         "brick": "CB-{}".format(sheet["concept_number"]), "key": "card:" + card["code"]}
    changes = [k for k in TEXT if card.get(k) and " ".join(card[k].split()) != " ".join(str(sheet.get(k) or "").split())]
    kind = card["kind"] if card["kind"] != sheet["kind"] else None
    if kind:
        changes.append("kind")
    if card.get("status") and card["status"] != sheet["status"] and sheet["status"] != "selected":
        changes.append("status")
    pic, pdf = split(names, files)
    slot = "attachment_id" if (kind or sheet["kind"]) == "scan" else "figure_id"
    if pic and _sha(conn, sheet[slot]) != hashlib.sha256(files[pic][0]).hexdigest():
        changes.append("image")
    own = slot == "figure_id" and sheet["attachment_id"] and sheet.get("file_mime") in DRAWABLE
    if own and "image" not in changes:
        changes.append("template")  # the sheet's own picture steps aside: drawn on the template
    if pdf and _sha(conn, sheet["pdf_id"]) != hashlib.sha256(files[pdf][0]).hexdigest():
        changes.append("pdf")
    e.update(changes=changes, slot=slot, replaces=bool(pic and sheet[slot]), new_kind=kind)
    if changes:
        e.update(status="update", reason="mise à jour : " + ", ".join(changes))
    else:
        e.update(status="exists", reason="déjà à jour")
    return e


def apply_update(ctx, pid, e, files, store):
    card, sheet = e["card"], ctx.conn.execute("SELECT * FROM diamond_concept_sheets WHERE id = ?", (e["sheet_id"],)).fetchone()
    sets = {}
    body = {k: card[k] for k in TEXT if k in e["changes"]}
    sets.update(S._fields(body, partial=True))
    if e.get("new_kind"):
        sets["kind"] = e["new_kind"]
    if "status" in e["changes"]:
        sets["status"] = card["status"]
    pic, pdf = split(e["files"], files)
    if "image" in e["changes"]:
        sets[e["slot"]] = store(ctx, pid, pic, *files[pic])
    if e["slot"] == "figure_id" and sheet["attachment_id"]:  # the sheet's own picture steps aside for the template
        row = ctx.conn.execute("SELECT mime FROM attachments WHERE id = ?", (sheet["attachment_id"],)).fetchone()
        if row is not None and row["mime"] in DRAWABLE:
            sets["attachment_id"] = None
            if "figure_id" not in sets and not sheet["figure_id"]:
                sets["figure_id"] = sheet["attachment_id"]  # no sketch in the answer: the old picture is drawn in the template
    if "pdf" in e["changes"]:
        sets["pdf_id"] = store(ctx, pid, pdf, *files[pdf])
    cols = ", ".join("{} = ?".format(k) for k in sets)
    ctx.conn.execute("UPDATE diamond_concept_sheets SET {}, updated_by = ?, updated_at = ? WHERE id = ?".format(cols),
                     tuple(sets.values()) + (ctx.user["id"], db.utc_now(), e["sheet_id"]))
    audit.log_action(ctx.conn, ctx.user["id"], "diamond_sheet_update", "diamond_concept_sheet", e["sheet_id"],
                     {"code": e["code"], "fields": sorted(sets), "source": "import", "previous_picture": sheet["attachment_id"]
                      if "attachment_id" in sets else None}, ctx.ip)
    return "mise à jour ({})".format(", ".join(e["changes"]))


def create(ctx, pid, e, files, store):
    """A new sheet of the answer: its text, its number, its sketch drawn on the template, its PDF, its status."""
    card = e["card"]
    fields = S._fields(dict({k: card.get(k) or "" for k in TEXT}, kind=card["kind"]))
    pic, pdf = split(e["files"], files)
    scan = fields["kind"] == "scan"
    pic_id = store(ctx, pid, pic, *files[pic]) if pic else None
    pdf_id = store(ctx, pid, pdf, *files[pdf]) if pdf else None
    if scan:
        sid = S.add(ctx.conn, ctx.user["id"], pid, e["concept_id"], fields, pic_id or pdf_id, number=card["number"],
                    pdf_id=pdf_id if pic_id else None)
    else:
        sid = S.add(ctx.conn, ctx.user["id"], pid, e["concept_id"], fields, None, number=card["number"], pdf_id=pdf_id,
                    figure_id=pic_id)
    if card.get("status"):
        ctx.conn.execute("UPDATE diamond_concept_sheets SET status = ? WHERE id = ?", (card["status"], sid))
    row = ctx.conn.execute("SELECT s.number, c.number AS cn FROM diamond_concept_sheets s JOIN diamond_concepts c ON c.id = s.concept_id "
                           "WHERE s.id = ?", (sid,)).fetchone()
    return sid, S.code(row["cn"], row["number"])
