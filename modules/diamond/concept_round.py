"""Diamond · « ↔ IA : feuilles de concept », the round trip of a creativity session with an AI assistant (0.60.132, D-O-145).

The one way concept sheets travel to and from an AI: an idea is its text AND its sketch, so the answer is a .zip (reponse.json and
images/<code>_<word>.png), never a JSON block alone (0.60.135, D-O-148: the JSON-only prompts of a brick are gone, and « ↔ IA » of
Diamond reads the sheets without writing them). Four scopes, as many rounds as the team wants (refinement, creativity):
  scope=all          every branch of the tree               (the legacy ?fid=all still works)
  scope=f<id>        one branch (a secondary function)      (the legacy ?fid=<id> still works)
  scope=c<id>        one brick, CB-n                        0.60.135
  scope=s<id>        one sheet, CB-n.m, to refine it        0.60.135: its code kept, its text and its sketch redone
  GET  /concepts/round?scope=…              the branches and the bricks (the choices), and the prompt of that scope
  GET  /concepts/round/context.zip?scope=…  when the scope has sheets: contexte.json, their sketches (images/) and PDF (pdf/),
                                            PROMPT.md -- what the assistant needs to build on the earlier rounds
  POST /concepts/round/import               the .zip the assistant hands back (or its reponse.json alone), applied at once:
                                            backup of the Space, new codes created on the template, existing codes updated,
                                            duplicates refused, one line per sheet in the report (concept_cards.run)
A frozen brick is left out of the prompt; the import refuses its sheets and says so. A branch without a brick « to define »
asks for pivots against its existing concepts instead of nothing.
"""
import io
import json
import re
import zipfile

from core import audit, terms, uploads
from core.errors import ApiError
from core.files import RawFile

from . import concept_cards as K
from . import concept_sheets as S
from . import concepts as C
from . import functions as F

COUNT, PIVOTS = 3, 2
PDF = "application/pdf"
SCOPE = re.compile(r"^(all|[fcs]\d+)$")
MARK = {"dropped": " [écartée]", "selected": " [retenue]"}

GUIDE = """Tu es ingénieur(e) produit dans l'équipe du projet « {name} ». Nous tenons une séance de créativité sur {scope}.
Voici les briques technologiques, leurs fonctions et les feuilles de concept déjà dessinées :

{bricks}
{needs}{context}
**Ta tâche**
{task}
- Pour améliorer une feuille existante, garde **son code exact** ({code_old}) : elle est mise à jour, jamais dupliquée.
- Une nouvelle feuille prend un **code nouveau**, à partir du « prochain code libre » de sa brique (ex. {code_new}, puis la suite).
- **Pas de doublon** : ne repropose pas une idée déjà listée, même écartée, sous un autre code ou un autre titre ; la plateforme
  refuse un code nouveau qui reprend le titre ou le principe d'une feuille de sa brique.
- Chaque feuille est une **idée complète : son texte ET son croquis**. Le texte : `code`, `concept` (CB-n), un `title` court qui
  parle, le `principle` en une phrase, une `description` (ce qu'on dessinerait : architecture, matériaux, ordres de grandeur),
  `pros`, `cons` et `questions` (une ligne chacun : essais, normes, ordres de grandeur à confirmer), un `badge` de deux à quatre
  mots (l'atout de la feuille), `kind` « ai », `status` « open ».
Pose-moi d'abord les questions qui te manquent ; nous itérerons ensemble avant que tu rendes le fichier. {terms}

**Ce que tu rends : un seul fichier .zip**, que la plateforme importe tel quel, sans autre manipulation :
- `reponse.json` : le bloc ci-dessous, une entrée par feuille nouvelle ou modifiée ;
- `images/<code>_<mot>.png` : le croquis de chaque feuille (PNG ou JPEG, fond blanc, trait foncé, environ 1600 × 1000 px), sans
  titre ni cadre : la plateforme le pose sur son gabarit avec le titre, le badge, les + / − / ? et le cartouche ;
- `pdf/<code>_<mot>.pdf` : facultatif, un document de la feuille.
Si tu ne peux pas créer de fichier, rends seulement le bloc `reponse.json` (les feuilles arriveront sans croquis : la zone de
dessin du gabarit restera vide jusqu'au prochain tour).

```json
{answer}
```"""

REFINE = ("- **Raffine la feuille {code} « {title} »** selon nos échanges : garde **son code exact** ({code}), reprends tout son "
          "texte (titre, principe, description, + / − / ?, badge) et **redessine son croquis** (`images/{code}_<mot>.png`), à "
          "partir de celui du fichier de contexte s'il y en a un. Rends cette seule feuille.\n"
          "- Ne touche pas aux autres feuilles de la brique ; si une variante vraiment différente apparaît en chemin, donne-lui le "
          "prochain code libre ({next}).")


def _project(conn, pid):
    return conn.execute("SELECT name, description FROM projects WHERE id = ?", (pid,)).fetchone()


def _requirements(conn, pid, limit=40):
    """The needs first, then the most critical requirements of the Space (when Agile is on)."""
    rows = conn.execute(
        "SELECT i.number, i.title, COALESCE(r.kind, 'requirement') AS kind, r.criticality FROM agile_issues i "
        "JOIN agile_issue_types t ON t.id = i.type_id AND t.is_requirement = 1 JOIN agile_statuses s ON s.id = i.status_id "
        "LEFT JOIN agile_requirements r ON r.issue_id = i.id WHERE i.project_id = ? AND s.name NOT IN ('Rejected', 'Obsolete') "
        "ORDER BY (COALESCE(r.kind, 'requirement') = 'need') DESC, COALESCE(NULLIF(r.criticality, ''), 'Z'), i.number LIMIT ?",
        (pid, limit)).fetchall()
    key = conn.execute("SELECT key FROM projects WHERE id = ?", (pid,)).fetchone()["key"]
    return ["- {}-{} {}{}".format(key, r["number"], "[Need] " if r["kind"] == "need" else "", r["title"]) for r in rows]


def branches(conn, pid):
    """The level-2 functions of the tree (the branches), each with its functions (ids)."""
    fns = F.rows(conn, pid)
    lv, tree = F.levels(fns), F.in_tree(fns)
    kids = {}
    for f in fns:
        kids.setdefault(f["parent_id"], []).append(f)
    out = []
    for f in fns:
        if f["id"] not in tree or lv.get(f["id"]) != 2:
            continue
        ids, todo = set(), [f]
        while todo:
            cur = todo.pop()
            ids.add(cur["id"])
            todo += kids.get(cur["id"], [])
        out.append({"id": f["id"], "number": f["number"], "text": f["text"], "ids": ids})
    return out, {f["id"]: f for f in fns}


def scope_key(query):
    """The scope asked: ?scope=all|f<id>|c<id>|s<id>, or the legacy ?fid=<id>|all of 0.60.132."""
    q = query or {}
    raw = str(q.get("scope") or "").strip().lower()
    if not raw:
        fid = str(q.get("fid") or "all").strip()
        raw = "all" if fid == "all" else "f" + fid
    if not SCOPE.match(raw):
        raise ApiError(400, "Portée « {} » inconnue. Correctif : toutes les branches, une branche, une brique ou une feuille."
                       .format(raw[:20]))
    return raw


def scope(conn, pid, key):
    """{label, tag, key, bricks (in scope, not frozen), frozen, focus (the sheet to refine), branches, brick_list, by_id}."""
    groups, by_id = branches(conn, pid)
    bricks = C.rows(conn, pid)
    out = {"key": key, "focus": None, "by_id": by_id,
           "branches": [{"id": b["id"], "label": "F{} {}".format(b["number"], b["text"]),
                         "bricks": sum(1 for c in bricks if set(c["function_ids"]) & b["ids"]),
                         "to_define": sum(1 for c in bricks if set(c["function_ids"]) & b["ids"] and c["kind"] == "to_define")}
                        for b in groups],
           "brick_list": [{"id": c["id"], "code": c["code"], "label": "{} « {} »".format(c["code"], c["initial_name"] or c["name"]),
                           "kind": c["kind"], "frozen": bool(c["frozen"]), "sheets": c["sheets"]} for c in bricks]}
    if key == "all":
        out.update(label="toutes les branches", tag="toutes")
        chosen = [c for c in bricks if c["function_ids"]]
    elif key[0] == "f":
        branch = next((b for b in groups if b["id"] == int(key[1:])), None)
        if branch is None:
            raise ApiError(400, "Branche inconnue. Correctif : choisissez une branche dans la liste, ou « Toutes les branches ».")
        out.update(label="la branche F{} « {} »".format(branch["number"], branch["text"]), tag="F{}".format(branch["number"]))
        chosen = [c for c in bricks if set(c["function_ids"]) & branch["ids"]]
    elif key[0] == "c":
        brick = next((c for c in bricks if c["id"] == int(key[1:])), None)
        if brick is None:
            raise ApiError(400, "Brique inconnue dans ce Space (archivée ?). Correctif : choisissez une brique dans la liste.")
        out.update(label="la brique {} « {} »".format(brick["code"], brick["initial_name"] or brick["name"]), tag=brick["code"])
        chosen = [brick]
    else:
        sheet = next((s for s in S.rows(conn, pid) if s["id"] == int(key[1:])), None)
        if sheet is None:
            raise ApiError(400, "Feuille de concept inconnue dans ce Space (archivée ou supprimée ?). Correctif : rechargez la page.")
        brick = next(c for c in bricks if c["id"] == sheet["concept_id"])
        out.update(label="la feuille {} « {} »".format(sheet["code"], sheet["title"]), tag=sheet["code"], focus=sheet,
                   sheet={"id": sheet["id"], "code": sheet["code"], "title": sheet["title"], "brick": brick["code"]})
        chosen = [brick]
    out.update(bricks=[c for c in chosen if not c["frozen"]], frozen=[c for c in chosen if c["frozen"]])
    return out


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").lower().encode("ascii", "ignore").decode()).strip("_")[:30] or "feuille"


def _files(conn, pid, sheet):
    """(picture attachment, pdf attachment) of a sheet: its sketch, else its own picture; its PDF, else a scan PDF."""
    ids = [sheet.get("figure_id"), sheet.get("attachment_id"), sheet.get("pdf_id")]
    rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM attachments WHERE project_id = ? AND id IN ({})"
                                                     .format(",".join("?" * 3)), [pid] + [i or 0 for i in ids])}
    pic = next((rows[i] for i in ids[:2] if i in rows and rows[i]["mime"] in uploads.IMAGE_TYPES), None)
    pdf = next((rows[i] for i in (ids[2], ids[1]) if i in rows and rows[i]["mime"] == PDF), None)
    return pic, pdf


def gather(conn, pid, bricks, focus=None):
    """{brick id: [sheet + picture, pdf file names]}, with the file name each gets in the context .zip. With a focus (the sheet
    to refine), only its files travel: the other sheets of the brick are there as text, so that nothing is proposed twice."""
    out = {}
    for c in bricks:
        items = []
        for s in S.rows(conn, pid, c["id"]):
            pic, pdf = _files(conn, pid, s) if focus is None or s["id"] == focus["id"] else (None, None)
            name = "{}_{}".format(s["code"], _slug(s["title"]))
            ext = uploads.IMAGE_TYPES[pic["mime"]][0] if pic else None
            items.append(dict(s, picture=pic, pdf=pdf, image_name="images/{}.{}".format(name, ext) if pic else None,
                              pdf_name="pdf/{}.pdf".format(name) if pdf else None))
        out[c["id"]] = items
    return out


def _task(sc, bricks, to_define, nxt):
    if sc["focus"]:
        return REFINE.format(code=sc["focus"]["code"], title=sc["focus"]["title"], next=nxt)
    if to_define:
        return ("- Pour chaque brique **à définir**, propose {} feuilles de concept **vraiment différentes** (principes physiques "
                "différents), en partant de son concept initial et des feuilles déjà dessinées, sans les répéter ; un pivot est "
                "bienvenu s'il sert mieux les besoins.".format(COUNT))
    return ("- {} : pour chacune, propose {} feuilles de **pivot** qui remettent le concept en question (une autre technologie, une "
            "autre architecture), comparables au concept existant face aux besoins et requirements."
            .format("Ces briques sont des **concepts existants**" if len(bricks) > 1 else "Cette brique est un **concept existant**",
                    PIVOTS))


def build_prompt(conn, pid, key):
    from modules.agile import common
    sc = scope(conn, pid, key)
    bricks, frozen, by_id, focus = sc["bricks"], sc["frozen"], sc["by_id"], sc["focus"]
    if not bricks:
        raise ApiError(409, "Aucune brique où dessiner sur {}{}. Correctif : rattachez les fonctions à des briques (panneau de la "
                       "fonction, dans l'arbre), ou défigez une brique.".format(sc["label"], " (briques figées : " + ", ".join(
                           c["code"] for c in frozen) + ")" if frozen else ""))
    sheets = gather(conn, pid, bricks, focus)
    lines = []
    for c in bricks:
        fns = ", ".join("F{} {}".format(by_id[i]["number"], by_id[i]["text"]) for i in c["function_ids"] if i in by_id)
        lines.append("- {} « {} » — {}{} ; fonctions : {}".format(
            c["code"], c["initial_name"] or c["name"], c["name"],
            " (concept existant : {})".format(c["reference"] or "—") if c["kind"] == "existing" else " (à définir)", fns or "—"))
        for s in sheets[c["id"]]:
            lines.append("    {}feuille {} « {} »{}{}{}".format(
                "→ À RAFFINER : " if focus and s["id"] == focus["id"] else "", s["code"], s["title"], MARK.get(s["status"], ""),
                " — " + s["principle"] if s["principle"] else "", " [croquis : {}]".format(s["image_name"]) if s["image_name"] else ""))
        lines.append("    prochain code libre : {}".format(S.code(c["number"], S.free_number(conn, c["id"]))))
    if frozen:
        lines.append("(Briques figées, laissées de côté : {}.)".format(", ".join(c["code"] for c in frozen)))
    to_define = [c for c in bricks if c["kind"] == "to_define"]
    reqs = _requirements(conn, pid) if common.is_enabled(conn, pid) else []
    n_files = sum(1 for items in sheets.values() for s in items if s["picture"] or s["pdf"])
    first = (to_define or bricks)[0]
    nxt = S.code(first["number"], S.free_number(conn, first["id"]))
    old = focus["code"] if focus else next((s["code"] for items in sheets.values() for s in items), None)
    shown = focus["code"] if focus else nxt
    answer = {"sheets": [{"code": shown, "concept": first["code"], "kind": "ai", "status": "open",
                          "title": focus["title"] if focus else "Titre court qui parle",
                          "principle": "Le principe en une phrase.", "description": "…", "pros": "…", "cons": "…",
                          "questions": "…", "badge": "deux à quatre mots", "image": "images/{}_croquis.png".format(shown)}]}
    text = GUIDE.format(
        name=_project(conn, pid)["name"], scope=sc["label"] + {"a": " de l'arbre fonctionnel, brique par brique", "f": " de l'arbre "
        "fonctionnel, brique par brique", "c": "", "s": ", une idée à la fois"}[key[0]], bricks="\n".join(lines),
        task=_task(sc, bricks, to_define, nxt),
        code_new=nxt, code_old="ex. " + old if old else "celui listé ci-dessus",
        needs=("\nBesoins et requirements du projet (les plus importants) :\n" + "\n".join(reqs) + "\n") if reqs else "",
        context=("\nLe fichier de contexte joint (.zip) contient les croquis et PDF des feuilles déjà dessinées (images/, pdf/) et "
                 "contexte.json : regarde-les avant de proposer.\n") if n_files else "",
        terms=terms.RULE_FR, answer=json.dumps(answer, ensure_ascii=False, indent=1))
    info = {"prompt": text, "scope": sc["label"], "key": key, "tag": sc["tag"], "branches": sc["branches"],
            "brick_list": sc["brick_list"], "sheet": sc.get("sheet"), "bricks": len(bricks), "to_define": len(to_define),
            "frozen": [c["code"] for c in frozen], "sheets": sum(len(v) for v in sheets.values()), "files": n_files}
    return info, bricks, sheets


def api_round(ctx):
    pid = F.access(ctx)
    key = scope_key(ctx.query)
    try:
        return build_prompt(ctx.conn, pid, key)[0]
    except ApiError as err:  # the choices still come back, with the reason
        if err.status != 409:
            raise
        sc = scope(ctx.conn, pid, key)
        return {"prompt": "", "error": err.message, "key": key, "scope": sc["label"], "tag": sc["tag"], "branches": sc["branches"],
                "brick_list": sc["brick_list"], "sheet": sc.get("sheet"), "bricks": 0, "to_define": 0, "sheets": 0, "files": 0,
                "frozen": [c["code"] for c in sc["frozen"]]}


def api_context(ctx):
    pid = F.access(ctx)
    key = scope_key(ctx.query)
    info, bricks, sheets = build_prompt(ctx.conn, pid, key)
    if not info["sheets"]:
        raise ApiError(409, "Aucune feuille encore dans {} : copiez seulement le prompt.".format(info["scope"]))
    ctx_json = {"scope": info["scope"], "focus": (info["sheet"] or {}).get("code", ""), "bricks": [], "sheets": []}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for c in bricks:
            ctx_json["bricks"].append({k: c[k] for k in ("code", "name", "initial_name", "kind", "reference")})
            for s in sheets[c["id"]]:
                ctx_json["sheets"].append(dict({k: s[k] or "" for k in ("code", "title", "principle", "description", "pros", "cons",
                                                                         "questions", "badge", "kind", "status")},
                                               concept=c["code"], image=s["image_name"] or "", pdf=s["pdf_name"] or ""))
                if s["picture"]:
                    z.writestr(s["image_name"], uploads.read(ctx.data_dir, s["picture"]))
                if s["pdf"]:
                    z.writestr(s["pdf_name"], uploads.read(ctx.data_dir, s["pdf"]))
        z.writestr("contexte.json", json.dumps(ctx_json, ensure_ascii=False, indent=1))
        z.writestr("PROMPT.md", info["prompt"])
    audit.log_action(ctx.conn, ctx.user["id"], "diamond_sheets_context", "project", pid,
                     {"scope": info["scope"], "sheets": info["sheets"], "files": info["files"]}, ctx.ip)
    return RawFile(buf.getvalue(), "contexte_feuilles_{}.zip".format(info["tag"]), "application/zip")


@uploads.large_body("max_evidence_mb")
def api_import(ctx):
    pid = F.access(ctx, "editor")
    data = getattr(getattr(ctx, "upload", None), "data", b"") or b""
    if not data:
        raise ApiError(400, "Aucun fichier reçu. Correctif : déposez le .zip rendu par l'assistant IA.")
    return K.run(ctx, pid, K.read_any(data), apply=True, strict=False)
