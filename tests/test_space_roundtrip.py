"""0.60.127 (D-O-140): a Space comes back whole -- the Rover of DEMO (every module, Diamond included, with a concept sheet using
the fields of 0.60.125: badge, questions, sketch, PDF) saved as .zip, deleted, then restored under its own key: every table of the
Space is identical, row for row (ids and links aside), and every link is kept. A new table tied to a Space by something else than
a foreign key would be missed by the backup: the first test says which."""
import base64
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core import auth, backup, db, modules, router, startup  # noqa: E402
from core.config import load_config  # noqa: E402
from tools.api_client import Client  # noqa: E402

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
HOOKED = {"datum_id", "decision_concept_id", "decision_alt_id"}  # ids renumbered by the modules' on_restore hooks


def fingerprint(key):
    with db.connect() as conn:
        pid = conn.execute("SELECT id FROM projects WHERE key = ?", (key,)).fetchone()[0]
        info, rows = backup.collect(conn, pid)
    out = {}
    for t, rs in rows.items():
        if t == "projects":
            continue
        fks = {col for col, _p, _pc in info[t]["fks"]}
        skip = fks | HOOKED | {"id", "__rowid"}
        out[t] = sorted(json.dumps({k: v for k, v in r.items() if k not in skip}, sort_keys=True, default=str) for r in rs)
        out[t + " (liens)"] = sum(1 for r in rs for col in fks if col != "project_id" and r.get(col) is not None)
    return out


class SpaceRoundTripTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        data_dir = Path(cls.tmp.name)
        cfg = load_config(data_dir)
        cfg["port"], cfg["require_initials"] = 0, False
        db.init_db(data_dir / "a.db", modules.registered_schema(), modules.registered_migrations())
        with db.connect() as conn:
            auth.ensure_initial_admin(conn, data_dir, dev_password="admin")
        startup.run(data_dir, cfg)
        cls.server = router.create_server(cfg, BASE_DIR / "static", data_dir)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.admin = Client("http://127.0.0.1:{}".format(cls.server.server_address[1]))
        cls.admin.login("admin", "admin")
        cls.pid = next(p["id"] for p in cls.admin.get("/api/me")["projects"] if p["key"] == "DEMO")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def test_01_every_table_of_a_space_is_reached(self):
        with db.connect() as conn:
            _info, rows = backup.collect(conn, self.pid)
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                                                 "AND sql NOT LIKE 'CREATE VIRTUAL%'")]
            missed = [t for t in tables if t not in rows and t not in backup.SKIP and t != "projects" and "_fts" not in t
                      and conn.execute('SELECT COUNT(*) FROM "{}"'.format(t)).fetchone()[0]]
        self.assertEqual(missed, [], "tables with rows that no Space backup reaches (no foreign key to the Space)")

    def test_02_backup_delete_restore_is_identical(self):
        base = "/api/diamond/p/{}".format(self.pid)
        brick = next(c for c in self.admin.get(base + "/concepts")["concepts"] if not c["frozen"])
        fig = self.admin.upload(base + "/sheets/upload", PNG, "image/png", "f.png")["id"]
        pdf = self.admin.upload(base + "/sheets/upload", PDF, "application/pdf", "f.pdf")["id"]
        self.admin.post(base + "/concepts/{}/sheets".format(brick["id"]), {"title": "Aller-retour", "badge": "sans outil",
                                                                            "questions": "? essai", "figure_id": fig, "pdf_id": pdf})
        before = fingerprint("DEMO")
        self.assertGreater(len(before), 100)
        status, _h, data = self.admin.raw_get("/api/admin/projects/{}/backup.zip".format(self.pid))
        self.assertEqual(status, 200)
        with db.connect() as conn:
            conn.execute("UPDATE projects SET is_archived = 1 WHERE id = ?", (self.pid,))
        self.admin.post("/api/admin/projects/{}/delete".format(self.pid), {"confirm_key": "DEMO"})
        done = self.admin.upload("/api/admin/restore", data, "application/zip", "demo.zip")
        self.assertEqual((done["project"]["key"], done["skipped"]), ("DEMO", {}))
        after = fingerprint("DEMO")
        self.assertEqual([t for t in sorted(set(before) | set(after)) if before.get(t) != after.get(t)], [])
        sheet = next(s for s in self.admin.get("/api/diamond/p/{}/sheets".format(done["project"]["id"]))["sheets"]
                     if s["title"] == "Aller-retour")
        self.assertTrue(sheet["figure_id"] and sheet["pdf_id"])
        status, _h, body = self.admin.raw_get("/api/diamond/p/{}/sheets/{}/file?which=pdf".format(done["project"]["id"], sheet["id"]))
        self.assertTrue(body.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
