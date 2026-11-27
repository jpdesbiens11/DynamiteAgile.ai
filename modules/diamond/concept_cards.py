"""Diamond · concept sheets imported by batch (0.60.125, D-O-138): the cards of a brainstorm, in the format the platform dictates,
with the picture and the PDF of each sheet, in one .zip.

    POST /sheets/import?mode=preview|apply[&cid=<brick>][&extras=1]   (raw body: the .zip)

The .zip holds
  - one or several cards files (.md) in the format of the platform:
        ## CB-3.2 — Bras articulé à ressort compensé
        **Principle:** Un ressort équilibre le poids de la tête : elle reste où on la lâche.
        (free lines: the description)
        + aucun réglage de vis ; geste naturel
        − fatigue du ressort
        ? durée de vie (n ≥ 10 000 cycles)
        **Badge:** sans outil
  - the pictures (PNG, JPEG) and PDF of the sheets, found by the code in their name (CB-3.2_bras_ressort.png).
A picture or a PDF without a card becomes a sheet of its own, titled from its name (CB-3.7_xxx.png); with extras=1, a file of
the brick only (CB-3_synthese.png) or without a code, too. The brick is the one of the code (CB-3 → brick 3), or `cid` for all.
A sheet keeps its number when it is free in the brick (CB-3.2 stays CB-3.2). Nothing is overwritten: a sheet of the same title
already in the brick is left as it is, so the same .zip can be imported twice. preview builds nothing; apply stores the files
(core/uploads.py, the same file is stored once) and creates the sheets.
0.60.129 (D-O-142): a picture or a PDF without a card whose name STARTS with the code of a sheet of the Space (CB-1.1_croquis.png,
CB-6.2-v2.jpg, CB-1.1.png) goes on that sheet instead of making a new one (concept_cards_attach.py); its nature stays as it is.
The preview has one line per sheet or file, each ticked (apply ?skip=<JSON list of keys> leaves out the unticked ones), and apply
writes a backup of the Space first.
0.60.131 (D-O-144): a reponse.json in the .zip ({"sheets": [...]}, the answer of « ↔ IA ») is read (concept_cards_json.py): a new
code creates an « ai » sheet with all its text and its sketch drawn on the template, an existing code updates its sheet; one line per
sheet of the answer in the preview and in the report of apply, never a silent skip or a Scan. Lines sorted CB-6.9 before CB-6.10.
"""
import io
import re
import zipfile

from core import audit, uploads, validate
from core.errors import ApiError

from . import concept_cards_attach as AT
from . import concept_cards_json as J
from . import concept_sheets as S
from . import concepts as C
from . import functions as F

MAX_ENTRIES, MAX_FILE_MB, MAX_TOTAL_MB = 300, 15, 120
HEAD = re.compile(r"^#{2,3}\s+(?:(CB-(\d+)\.(\d+))\s*[—–:-]+\s*)?(.+?)\s*$")
FIELD = re.compile(r"^\*\*\s*(Principle|Principe|Badge|Description|Questions?)\s*:?\s*\*\*\s*:?\s*(.*)$", re.I)
SHEET_CODE = re.compile(r"CB-(\d+)\.(\d+)(?!\d|-\d)", re.I)  # not a range (CB-3.1-3.6_brainwriting.pdf: the brick's)
BRICK_CODE = re.compile(r"CB-(\d+)", re.I)
RANGE = re.compile(r"CB-\d+\.\d+-\d+(?:\.\d+)?", re.I)
KINDS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".pdf": "application/pdf"}


def parse_cards(text):
    """The cards of a .md file: [{code, brick, number, title, principle, description, pros, cons, questions, badge}]."""
    cards, cur = [], None
    for raw in str(text or "").splitlines():
        line = raw.strip()
        head = HEAD.match(line)
        if head and line.startswith("##"):
            cur = {"code": (head.group(1) or "").upper() or None, "brick": int(head.group(2)) if head.group(2) else None,
                   "number": int(head.group(3)) if head.group(3) else None, "title": head.group(4).strip(" *"),
                   "principle": "", "description": [], "pros": [], "cons": [], "questions": [], "badge": ""}
            cards.append(cur)
            continue
        if cur is None or not line or line.startswith("#"):
            continue
        field = FIELD.match(line)
        if field:
            name, value = field.group(1).lower(), field.group(2).strip()
            if name in ("principle", "principe"):
                cur["principle"] = value
            elif name == "badge":
                cur["badge"] = value
            elif name.startswith("question"):
                cur["questions"].append(value)
            else:
                cur["description"].append(value)
        elif line[0] == "+":
            cur["pros"].append(line[1:].strip())
        elif line[0] in "−–" or line.startswith("- "):
            cur["cons"].append(line[1:].strip())
        elif line[0] == "?":
            cur["questions"].append(line[1:].strip())
        else:
            cur["description"].append(line)
    for c in cards:
        for name in ("description", "pros", "cons", "questions"):
            c[name] = "\n".join(v for v in c[name] if v)
    return cards


def read_zip(data):
    """{cards: [...], files: {name: (bytes, mime)}} of the .zip, with its limits (a zip bomb stops at the header)."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ApiError(415, "Ce fichier n'est pas un .zip. Correctif : compressez les cartes (.md), les PNG et les PDF dans un .zip.")
    infos = [i for i in z.infolist() if not i.is_dir()]
    if len(infos) > MAX_ENTRIES:
        raise ApiError(413, "{} fichiers dans le .zip : {} au maximum.".format(len(infos), MAX_ENTRIES))
    if sum(i.file_size for i in infos) > MAX_TOTAL_MB * 1048576:
        raise ApiError(413, "Le .zip décompressé dépasse {} Mo. Correctif : importez les briques une à une.".format(MAX_TOTAL_MB))
    cards, files, warnings = [], {}, []
    for info in infos:
        name = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
        if not name or name.startswith(".") or info.filename.startswith("__MACOSX"):
            continue
        ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in KINDS and ext not in (".md", ".txt", ".json"):
            continue
        if info.file_size > MAX_FILE_MB * 1048576:
            raise ApiError(413, "« {} » fait plus de {} Mo.".format(name, MAX_FILE_MB))
        body = z.read(info)
        if ext == ".json":  # 0.60.131 (D-O-144): the AI's answer, read (was left aside in 0.60.129)
            got, said = J.read(name, body)
            cards += got
            warnings += said
        elif ext in (".md", ".txt"):
            cards += parse_cards(body.decode("utf-8", "replace"))
        else:
            files[name] = (body, KINDS[ext])
    return {"cards": cards, "files": files, "warnings": warnings}


def _norm(text):
    return re.sub(r"[^\w]+", " ", str(text or "").lower()).strip()


def _title_of(name):
    stem = name.rsplit(".", 1)[0]
    stem = RANGE.sub("", stem)
    stem = SHEET_CODE.sub("", stem)
    stem = BRICK_CODE.sub("", stem)
    return " ".join(stem.replace("_", " ").replace("-", " ").split()).capitalize() or name


def plan(conn, pid, pack, target=None, extras=False):
    """What the import would do: one entry per sheet, and the files left aside."""
    bricks = {c["number"]: c for c in C.rows(conn, pid)}
    have, active = {}, {}
    for s in S.rows(conn, pid):
        have.setdefault(s["concept_id"], set()).add(_norm(s["title"]))
        active[s["code"]] = s
    archived = AT._sheets(conn, pid)[1]
    used, entries = set(), []
    by_code = {}
    for name in sorted(pack["files"]):
        m = SHEET_CODE.search(name)
        if m:
            by_code.setdefault("CB-{}.{}".format(int(m.group(1)), int(m.group(2))), []).append(name)

    def entry(card, names, kind):
        brick = target or bricks.get(card["brick"])
        e = {"code": card["code"], "title": card["title"], "files": names, "kind": kind, "card": card}
        by_title = not (card.get("source") == "json" and card["code"])  # 0.60.131: a code of the answer is its identity
        if card.get("error"):
            e.update(status="refused", reason=card["error"])
        elif brick is None:
            e.update(status="refused", reason="brique CB-{} introuvable dans ce Space : créez-la, ou choisissez la brique cible"
                     .format(card["brick"]) if card["brick"] else "aucun code CB-n.m : choisissez la brique cible")
        elif brick.get("frozen"):
            e.update(status="refused", reason="{} est figée".format(brick["code"]))
        elif by_title and _norm(card["title"]) in have.get(brick["id"], set()):
            e.update(status="exists", brick=brick["code"], reason="une feuille de ce titre existe déjà dans " + brick["code"])
        else:
            e.update(status="new", brick=brick["code"], concept_id=brick["id"])
            have.setdefault(brick["id"], set()).add(_norm(card["title"]))
        entries.append(e)

    seen = set()
    for card in pack["cards"]:
        names = by_code.get(card["code"] or "", [])
        if card.get("source") == "json":  # 0.60.131 (D-O-144)
            names = J.files_of(card, names, pack["files"])
            used.update(names)
            sheet = active.get(card["code"]) if card["code"] and not target else None
            if card["code"] in seen:
                card["error"] = "{} en double dans la réponse : seule la première est retenue".format(card["code"])
            seen.add(card["code"])
            if sheet is not None and not card.get("error"):
                e = J.update_entry(conn, card, sheet, names, pack["files"])
                if sheet["concept_id"] in {b["id"] for b in bricks.values() if b.get("frozen")}:
                    e.update(status="refused", reason="{} est figée".format(e["brick"]))
                entries.append(e)
            else:
                entry(card, names, card["kind"])
                if card["code"] in archived and entries[-1]["status"] == "new":
                    entries[-1]["warning"] = "{} est archivée : la feuille prend le numéro libre suivant".format(card["code"])
            lost = J.missing(card, pack["files"])
            if lost:
                entries[-1]["warning"] = "{} : fichier absent du .zip : {}".format(card["code"] or card["title"], ", ".join(lost))
            continue
        used.update(names)
        entry(card, names, "ai")
    for e in entries:
        e["key"] = "card:" + (e["code"] or e["title"])
    attached, warnings = AT.plan(conn, pid, pack["files"], used)  # 0.60.129 (D-O-142): onto the sheet of the code
    for code in list(by_code):
        by_code[code] = [n for n in by_code[code] if n not in used]
        if not by_code[code]:
            del by_code[code]
    for code, names in by_code.items():
        if not set(names) & used:
            used.update(names)
            m = SHEET_CODE.search(code)
            entry({"code": code, "brick": int(m.group(1)), "number": int(m.group(2)), "title": _title_of(names[0])}, names, "scan")
            entries[-1]["warning"] = warnings.get(code)
    left = sorted(n for n in pack["files"] if n not in used)
    if extras:  # the picture and the PDF of the same name make one sheet (CB-3_synthese.png and .pdf)
        groups = {}
        for name in left:
            groups.setdefault(name.rsplit(".", 1)[0], []).append(name)
        for names in groups.values():
            m = BRICK_CODE.search(names[0])
            entry({"code": None, "brick": int(m.group(1)) if m else None, "number": None, "title": _title_of(names[0])}, names, "scan")
        left = []
    for e in entries:
        e.setdefault("key", "file:" + e["files"][0] if e["files"] else "card:" + str(e["code"] or e["title"]))
        if e["status"] in ("new", "update"):
            bad = AT.unreadable(e["files"], pack["files"])
            if bad:
                e.update(status="refused", reason=bad)
    out = attached + entries
    out.sort(key=lambda e: J.code_key(e.get("code")))  # 0.60.131: CB-6.9 before CB-6.10
    return out, left


def _store(ctx, pid, name, data, mime):
    ctx.upload = uploads.Upload(data, mime, name)
    limit = MAX_FILE_MB * 1048576
    row = uploads.store_pdf(ctx, pid, S.MODULE, limit) if mime == "application/pdf" else uploads.store_image(ctx, pid, S.MODULE, limit)
    return row["id"]


@uploads.large_body("max_evidence_mb")  # 0.60.129 (D-O-142): a batch of 40 sketches is bigger than « max_upload_mb »
def api_import(ctx):
    pid = F.access(ctx, "editor")
    data = getattr(getattr(ctx, "upload", None), "data", b"") or b""
    if not data:
        raise ApiError(400, "Aucun fichier reçu. Correctif : choisissez le .zip des feuilles de concept.")
    q = ctx.query or {}
    target = None
    if q.get("cid"):
        target = next((c for c in C.rows(ctx.conn, pid) if c["id"] == validate.int_param(q, "cid")), None)
        if target is None:
            raise ApiError(404, "Brique cible introuvable dans ce Space (archivée ?). Correctif : rechargez la page.")
    pack = read_zip(data)
    if not pack["cards"] and not pack["files"]:
        raise ApiError(400, "Le .zip ne contient ni carte (.md ou reponse.json) ni image ni PDF." + "".join(" ⚠ " + w for w in pack["warnings"]))
    entries, left = plan(ctx.conn, pid, pack, target, str(q.get("extras") or "") in ("1", "true"))
    counts = {k: sum(1 for e in entries if e["status"] == k) for k in ("new", "update", "attach", "exists", "refused")}
    view = [{k: e.get(k) for k in ("key", "code", "title", "files", "status", "reason", "brick", "kind", "action", "replaces",
                                   "warning", "changes")} for e in entries]
    warnings = pack["warnings"] + [e["warning"] for e in entries if e.get("warning")]
    if q.get("mode") != "apply":
        return {"entries": view, "left": left, "counts": counts, "cards": len(pack["cards"]), "files": len(pack["files"]),
                "warnings": warnings}
    skip = AT.skip_keys(q.get("skip"))
    todo = [e for e in entries if e["status"] in ("new", "update", "attach") and e["key"] not in skip]
    if not todo:
        raise ApiError(409, "Rien à importer : ces feuilles sont déjà dans le Space, refusées ou décochées (voir l'aperçu).")
    from .import_merge import backup
    saved = backup(ctx, pid)  # 0.60.129 (D-O-142): as for the other imports, a backup of the Space first
    attached = AT.apply(ctx, pid, [e for e in todo if e["status"] == "attach"], pack["files"], _store)
    outcome = {e["key"]: "fichier posé sur " + e["code"] for e in todo if e["status"] == "attach"}
    created, updated = [], []
    for e in todo:
        if e["status"] == "update":
            outcome[e["key"]] = J.apply_update(ctx, pid, e, pack["files"], _store)
            updated.append(e["code"])
            continue
        if e["status"] != "new":
            continue
        card = e["card"]
        if card.get("source") == "json":
            sid, made = J.create(ctx, pid, e, pack["files"], _store)
            created.append(sid)
            outcome[e["key"]] = "créée " + made + (" (au lieu de {})".format(e["code"]) if e["code"] and made != e["code"] else "")
            continue
        fields = S._fields(dict({k: card.get(k) or "" for k in S.LIMITS}, kind=e["kind"]))
        pics = [n for n in e["files"] if pack["files"][n][1] != "application/pdf"]
        pdfs = [n for n in e["files"] if pack["files"][n][1] == "application/pdf"]
        main = pics[0] if pics else (pdfs[0] if pdfs else None)
        main_id = _store(ctx, pid, main, *pack["files"][main]) if main else None
        pdf_id = _store(ctx, pid, pdfs[0], *pack["files"][pdfs[0]]) if pics and pdfs else None
        sid = S.add(ctx.conn, ctx.user["id"], pid, e["concept_id"], fields, main_id, number=card.get("number"), pdf_id=pdf_id)
        created.append(sid)
        outcome[e["key"]] = "créée"
    audit.log_action(ctx.conn, ctx.user["id"], "diamond_sheets_import", "project", pid,
                     dict(counts, sheets=created, updated=updated, attached=attached, skipped=len(skip), files=len(pack["files"]),
                          backup=saved), ctx.ip)
    for line in view:  # 0.60.131 (D-O-144): the report, one line per sheet or file
        line["outcome"] = outcome.get(line["key"]) or ("décochée" if line["key"] in skip else "rien à faire : " + (line["reason"] or ""))
    return {"entries": view, "left": left, "counts": counts, "created": len(created), "updated": len(updated),
            "attached": len(attached), "backup": saved, "warnings": warnings, "imported": True}
