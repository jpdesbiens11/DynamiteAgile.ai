"""Diamond · « ↔ IA : feuilles de concept », the round trip of a creativity session with an AI assistant (0.60.132, D-O-145).

One screen, two steps, for one branch of the tree or all of them, as many rounds as the team wants (refinement, creativity):
  GET  /concepts/round?fid=<id|all>              the branches, and the prompt of that scope (shown in full, « Copier le prompt »)
  GET  /concepts/round/context.zip?fid=<id|all>  when the scope has sheets: contexte.json, their sketches (images/) and PDF (pdf/),
                                                 PROMPT.md -- what the assistant needs to build on the earlier rounds
  POST /concepts/round/import                    the .zip the assistant hands back (or its reponse.json alone), applied at once:
                                                 backup of the Space, new codes created on the template, existing codes updated,
                                                 one line per sheet in the report (concept_cards.run, concept_cards_json.py)
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
from .concept_ai import _project, _requirements

COUNT, PIVOTS = 3, 2
PDF = "application/pdf"

GUIDE = """Tu es ingénieur(e) produit dans l'équipe du projet « {name} ». Nous tenons une séance de créativité sur {scope} de
l'arbre fonctionnel, brique technologique par brique. Voici les briques, leurs fonctions et les feuilles de concept déjà dessinées :

{bricks}
{needs}{context}
**Ta tâche**
{task}
- Pour améliorer une feuille existante, garde **son code exact** ({code_old}) : elle est mise à jour, jamais dupliquée.
- Une nouvelle feuille prend un **code nouveau**, à partir du « prochain code libre » de sa brique (ex. {code_new}, puis la suite).
- Pour chaque feuille : `code`, `concept` (CB-n), un `title` court qui parle, le `principle` en une phrase, une `description` (ce
  qu'on dessinerait : architecture, matériaux, ordres de grandeur), `pros`, `cons` et `questions` (une ligne chacun : essais,
  normes, ordres de grandeur à confirmer), un `badge` de deux à quatre mots (l'atout de la feuille), `kind` « ai », `status` « open ».
Pose-moi d'abord les questions qui te manquent ; nous itérerons ensemble avant que tu rendes le fichier. {terms}

**Ce que tu rends : un seul fichier .zip**, que la plateforme importe tel quel, sans autre manipulation :
- `reponse.json` : le bloc ci-dessous, une entrée par feuille nouvelle ou modifiée ;
- `images/<code>_<mot>.png` : le croquis de chaque feuille (PNG ou JPEG, fond blanc, trait foncé, environ 1600 × 1000 px), sans
  titre ni cadre : la plateforme le pose sur son gabarit avec le titre, le badge, les + / − / ? et le cartouche ;
- `pdf/<code>_<mot>.pdf` : facultatif, un document de la feuille.
Si tu ne peux pas créer de fichier, rends seulement le bloc `reponse.json` (les feuilles arriveront sans croquis).

```json
{answer}
```"""


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


def scope(conn, pid, fid):
    """(label, bricks in scope, frozen bricks left out, the branches with their counts)."""
    groups, by_id = branches(conn, pid)
    bricks = C.rows(conn, pid)
    view = [{"id": b["id"], "label": "F{} {}".format(b["number"], b["text"]),
             "bricks": sum(1 for c in bricks if set(c["function_ids"]) & b["ids"]),
             "to_define": sum(1 for c in bricks if set(c["function_ids"]) & b["ids"] and c["kind"] == "to_define")} for b in groups]
    fid = str(fid or "all")
    if fid == "all":
        label, chosen = "toutes les branches", [c for c in bricks if c["function_ids"]]
    else:
        branch = next((b for b in groups if str(b["id"]) == fid), None)
        if branch is None:
            raise ApiError(400, "Branche inconnue. Correctif : choisissez une branche dans la liste, ou « Toutes les branches ».")
        label = "la branche F{} « {} »".format(branch["number"], branch["text"])
        chosen = [c for c in bricks if set(c["function_ids"]) & branch["ids"]]
    return label, [c for c in chosen if not c["frozen"]], [c for c in chosen if c["frozen"]], view, by_id


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


def gather(conn, pid, bricks):
    """{brick id: [sheet + picture, pdf file names]}, with the file name each gets in the context .zip."""
    out = {}
    for c in bricks:
        items = []
        for s in S.rows(conn, pid, c["id"]):
            pic, pdf = _files(conn, pid, s)
            name = "{}_{}".format(s["code"], _slug(s["title"]))
            ext = uploads.IMAGE_TYPES[pic["mime"]][0] if pic else None
            items.append(dict(s, picture=pic, pdf=pdf, image_name="images/{}.{}".format(name, ext) if pic else None,
                              pdf_name="pdf/{}.pdf".format(name) if pdf else None))
        out[c["id"]] = items
    return out


def build_prompt(conn, pid, fid):
    from modules.agile import common
    label, bricks, frozen, view, by_id = scope(conn, pid, fid)
    if not bricks:
        raise ApiError(409, "Aucune brique où dessiner sur {}{}. Correctif : rattachez les fonctions à des briques (panneau de la "
                       "fonction, dans l'arbre), ou défigez une brique.".format(label, " (briques figées : " + ", ".join(
                           c["code"] for c in frozen) + ")" if frozen else ""))
    sheets = gather(conn, pid, bricks)
    lines = []
    for c in bricks:
        fns = ", ".join("F{} {}".format(by_id[i]["number"], by_id[i]["text"]) for i in c["function_ids"] if i in by_id)
        lines.append("- {} « {} » — {}{} ; fonctions : {}".format(
            c["code"], c["initial_name"] or c["name"], c["name"],
            " (concept existant : {})".format(c["reference"] or "—") if c["kind"] == "existing" else " (à définir)", fns))
        for s in sheets[c["id"]]:
            lines.append("    feuille {} « {} »{}{}".format(s["code"], s["title"], " — " + s["principle"] if s["principle"] else "",
                                                          " [croquis : {}]".format(s["image_name"]) if s["image_name"] else ""))
        lines.append("    prochain code libre : {}".format(S.code(c["number"], S.free_number(conn, c["id"]))))
    if frozen:
        lines.append("(Briques figées, laissées de côté : {}.)".format(", ".join(c["code"] for c in frozen)))
    to_define = [c for c in bricks if c["kind"] == "to_define"]
    if to_define:
        task = ("- Pour chaque brique **à définir**, propose {} feuilles de concept **vraiment différentes** (principes physiques "
                "différents), en partant de son concept initial et des feuilles déjà dessinées, sans les répéter ; un pivot est "
                "bienvenu s'il sert mieux les besoins.".format(COUNT))
    else:
        task = ("- Ces briques sont des **concepts existants** : pour chacune, propose {} feuilles de **pivot** qui remettent le concept "
                "en question (une autre technologie, une autre architecture), comparables au concept existant face aux besoins et "
                "requirements.".format(PIVOTS))
    reqs = _requirements(conn, pid) if common.is_enabled(conn, pid) else []
    n_files = sum(1 for items in sheets.values() for s in items if s["picture"] or s["pdf"])
    first = (to_define or bricks)[0]
    nxt = S.code(first["number"], S.free_number(conn, first["id"]))
    old = next((s["code"] for items in sheets.values() for s in items), None)
    answer = {"sheets": [{"code": nxt, "concept": first["code"], "kind": "ai", "status": "open", "title": "Titre court qui parle",
                          "principle": "Le principe en une phrase.", "description": "…", "pros": "…", "cons": "…",
                          "questions": "…", "badge": "deux à quatre mots", "image": "images/{}_croquis.png".format(nxt)}]}
    text = GUIDE.format(
        name=_project(conn, pid)["name"], scope=label, bricks="\n".join(lines), task=task, code_new=nxt,
        code_old="ex. " + old if old else "celui listé ci-dessus",
        needs=("\nBesoins et requirements du projet (les plus importants) :\n" + "\n".join(reqs) + "\n") if reqs else "",
        context=("\nLe fichier de contexte joint (.zip) contient les croquis et PDF des feuilles déjà dessinées (images/, pdf/) et "
                 "contexte.json : regarde-les avant de proposer.\n") if n_files else "",
        terms=terms.RULE_FR, answer=json.dumps(answer, ensure_ascii=False, indent=1))
    return {"prompt": text, "scope": label, "branches": view, "bricks": len(bricks), "to_define": len(to_define),
            "frozen": [c["code"] for c in frozen], "sheets": sum(len(v) for v in sheets.values()), "files": n_files}, bricks, sheets


def api_round(ctx):
    pid = F.access(ctx)
    fid = (ctx.query or {}).get("fid") or "all"
    try:
        return build_prompt(ctx.conn, pid, fid)[0]
    except ApiError as err:  # the list of branches still comes back, with the reason
        if err.status != 409:
            raise
        return {"prompt": "", "error": err.message, "branches": scope(ctx.conn, pid, fid)[3], "bricks": 0, "sheets": 0, "files": 0}


def api_context(ctx):
    pid = F.access(ctx)
    fid = (ctx.query or {}).get("fid") or "all"
    info, bricks, sheets = build_prompt(ctx.conn, pid, fid)
    if not info["sheets"]:
        raise ApiError(409, "Aucune feuille encore dans {} : copiez seulement le prompt.".format(info["scope"]))
    ctx_json = {"scope": info["scope"], "bricks": [], "sheets": []}
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
    name = "contexte_feuilles_{}.zip".format("toutes" if str(fid) == "all" else "F" + re.sub(r"\D", "", info["scope"].split("«")[0]))
    return RawFile(buf.getvalue(), name, "application/zip")


@uploads.large_body("max_evidence_mb")
def api_import(ctx):
    pid = F.access(ctx, "editor")
    data = getattr(getattr(ctx, "upload", None), "data", b"") or b""
    if not data:
        raise ApiError(400, "Aucun fichier reçu. Correctif : déposez le .zip rendu par l'assistant IA.")
    return K.run(ctx, pid, K.read_any(data), apply=True, strict=False)
