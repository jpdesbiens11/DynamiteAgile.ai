"""Diamond · « ↔ IA » (0.60.111, D-O-124): the routes of the round trip -- the sections, the prompt, the .json, the answer read,
previewed and applied (moved out of rt.py in 0.60.135, D-O-148, where the engine stays).
"""
import json
import re
from collections import Counter

from core import audit, permissions, validate
from core.errors import ApiError
from core.files import RawFile

from . import ai_io
from .rt import KINDS, RoundTrip, apply, context, dump, plan


# ---------------------------------------------------------------- reading the answer

def read_doc(text):
    text = str(text or "").lstrip("﻿")
    if not text.strip():
        raise ApiError(400, "Réponse vide. Correctif : collez la réponse de l'assistant IA (son bloc JSON) ou choisissez le .json.")
    if len(text) > ai_io.MAX_TEXT:
        raise ApiError(413, "Texte trop long ({} caractères au plus).".format(ai_io.MAX_TEXT))
    blocks = re.findall(r"```(?:json)?[ \t]*\n(.*?)```", text, re.S)
    for body in reversed(blocks) if blocks else [text]:
        start, end = body.find("{"), body.rfind("}")
        if 0 <= start < end:
            try:
                data = json.loads(body[start:end + 1])
            except ValueError:
                continue
            if isinstance(data, dict):
                return data.get("diamond") if isinstance(data.get("diamond"), dict) else data
    raise ApiError(400, "Aucun objet JSON lu. Correctif : la réponse doit contenir un bloc ```json { \"functions\": [...], ... } ```.")


# ---------------------------------------------------------------- routes

def _pid(ctx, minimum):
    pid = validate.int_param(ctx.params, "pid")
    permissions.require_project_role(ctx.conn, ctx.user, pid, minimum)
    return pid


def _keys(rt, raw):
    keys = [k for k in str(raw or "").split(",") if k in rt.sections and rt.sections[k].listed]
    return keys or [k for k, s in rt.sections.items() if s.listed]


def api_sections(ctx):
    pid = _pid(ctx, "reader")
    rt = RoundTrip(ctx, pid)
    return {"sections": [{"key": s.key, "label": s.label, "pages": s.pages, "count": len(rt.records(s.key)), "read_only": bool(s.writes),
                          "writes": s.writes} for s in rt.sections.values()
                         if s.listed]}


def api_export(ctx):
    pid = _pid(ctx, "reader")
    rt = RoundTrip(ctx, pid)
    keys = _keys(rt, ctx.query.get("sections"))
    doc = dict(dump(rt, keys), _context=context(rt, keys))
    key = ctx.conn.execute("SELECT key FROM projects WHERE id = ?", (pid,)).fetchone()[0]
    return RawFile((json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8"),
                   "{}_diamond_{}.json".format(key, "-".join(keys) if len(keys) < 4 else "complet"), "application/json")


def api_prompt(ctx):
    from . import rt_prompt
    pid = _pid(ctx, "reader")
    rt = RoundTrip(ctx, pid)
    keys = _keys(rt, ctx.query.get("sections"))
    mode = ctx.query.get("mode") if ctx.query.get("mode") in rt_prompt.MODES else "review"
    board = None
    if str(ctx.query.get("ideation") or "").isdigit():  # 0.60.112 (D-O-125): the post-its of an Idéation session as source
        from modules.toolbox import ideation_ai
        board = ideation_ai.board(ctx.conn, pid, int(ctx.query["ideation"]))
    return {"prompt": rt_prompt.build(rt, keys, mode, ctx.query.get("goal", ""), board), "sections": keys}


def api_import(ctx):
    pid = _pid(ctx, "editor")
    rt = RoundTrip(ctx, pid)
    doc = read_doc(ctx.body.get("file"))
    entries, warnings = plan(rt, doc)
    counts = Counter(e["kind"] for e in entries)
    public = [{k: v for k, v in e.items() if not k.startswith("_")} for e in entries]
    summary = {k: counts.get(k, 0) for k in KINDS}
    labels = {k: rt.sections[k].label for k in {e["section"] for e in entries}}
    if ctx.body.get("mode") != "apply":
        apply(rt, entries, set(), dry=True)  # the rehearsal: what the pages' routes would refuse, refused now
        counts = Counter(e["kind"] for e in entries)
        summary = {k: counts.get(k, 0) for k in KINDS}
        public = [{k: v for k, v in e.items() if not k.startswith("_")} for e in entries]
        return {"mode": "preview", "entries": public, "counts": summary, "warnings": warnings, "labels": labels}
    skip = {str(x) for x in ctx.body.get("skip") or []}
    forced = {str(x) for x in ctx.body.get("confirm") or []}  # lines unticked by default that the person ticked herself:
    # the removals of a truncated section, and (0.60.135, D-O-148) the probable duplicates of an AI
    skip |= {e["id"] for e in entries if e["kind"] in ("remove", "new") and not e["default"] and e["id"] not in forced}
    apply(rt, entries, skip, dry=True)  # the same rehearsal: what the routes refuse now (a line it hung on was unticked) stays out
    if not [e for e in entries if e["kind"] in ("new", "update", "remove") and e["id"] not in skip]:
        raise ApiError(400, "Rien à appliquer : toutes les lignes sont identiques, refusées ou décochées.")
    from .import_merge import backup
    saved = backup(ctx, pid)
    with audit.source("ai"):  # 0.60.120 (D-O-133): « Changements » shows these lines as written by the AI
        done = apply(RoundTrip(ctx, pid), entries, skip)  # a fresh view of the Space: the rehearsal's ids are gone
        counts = Counter(e["kind"] for e in entries)
        audit.log_action(ctx.conn, ctx.user["id"], "diamond_rt_import", "project", pid,
                         dict(done, refused=counts.get("refused", 0), sections=sorted(labels), backup=saved), ctx.ip)
    return {"mode": "apply", "applied": {k: done.get(k, 0) for k in ("new", "update", "remove")},
            "refused": counts.get("refused", 0), "backup": saved}
