"""Diamond · « Revue » of the concept sheets (0.60.133, D-O-146): one sheet at a time, next / previous across bricks and branches
(static/js/diamond/concept_review.js). The review is shared by the team: a sheet seen is marked (reviewed_at, reviewed_by,
migration diamond 23) so the page counts « 30 / 45 vues » for everyone.

    POST /sheets/<sid>/review {action}   keep    seen; a « Dropped » sheet is back in the running (« Open »), 0.60.134 (D-O-147)
                                         drop    seen and « Dropped » (reversible; a Pugh matrix shows it dropped)
                                         reopen  back to « Open » and not seen
Deleting a sheet stays DELETE /sheets/<sid> (concept_sheets.api_delete: refused for a sheet a Pugh matrix uses or retained); the
screen sends it only after its 5-second « Annuler ». A frozen brick takes no change (concept_freeze.guard).
"""
from core import audit, db, validate
from core.errors import ApiError

from . import concept_sheets as S
from . import functions as F

ACTIONS = ("keep", "drop", "reopen")


def api_review(ctx):
    pid = F.access(ctx, "editor")
    s = S._sheet(ctx.conn, pid, validate.int_param(ctx.params, "sid"))
    action = str((ctx.body or {}).get("action") or "")
    if action not in ACTIONS:
        raise ApiError(400, "Action « {} » inconnue. Correctif : {}.".format(action[:20], ", ".join(ACTIONS)))
    from .concept_freeze import guard
    guard(ctx.conn, pid, s["concept_id"], "Revoir une feuille de concept")
    now = db.utc_now()
    if action == "keep":
        sets = {"reviewed_at": now, "reviewed_by": ctx.user["id"]}
        if s["status"] == "dropped":  # 0.60.134 (D-O-147): keeping a dropped sheet puts it back in the running
            sets["status"] = "open"
    elif action == "drop":
        if s["status"] == "selected":
            raise ApiError(409, "Cette feuille est retenue par une matrice de Pugh : elle ne peut pas être écartée ici. "
                                "Correctif : rouvrez la décision de la matrice.")
        sets = {"status": "dropped", "reviewed_at": now, "reviewed_by": ctx.user["id"]}
    else:
        sets = {"reviewed_at": None, "reviewed_by": None}
        if s["status"] == "dropped":
            sets["status"] = "open"
    cols = ", ".join("{} = ?".format(k) for k in sets)
    ctx.conn.execute("UPDATE diamond_concept_sheets SET {}, updated_by = ?, updated_at = ? WHERE id = ?".format(cols),
                     tuple(sets.values()) + (ctx.user["id"], now, s["id"]))
    audit.log_action(ctx.conn, ctx.user["id"], "diamond_sheet_review", "diamond_concept_sheet", s["id"],
                     {"action": action, "status": sets.get("status", s["status"])}, ctx.ip)
    return {"sheet": next(r for r in S.rows(ctx.conn, pid, s["concept_id"]) if r["id"] == s["id"])}
