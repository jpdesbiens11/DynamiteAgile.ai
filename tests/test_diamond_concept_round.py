"""0.60.132 (D-O-145): Diamond -- « ↔ IA : feuilles de concept », the round trip with an AI assistant: one branch or all of them,
the prompt shown in full (codes kept to update, next free code to create, a .zip asked in return), the context .zip when the scope has
sheets (contexte.json, images/, pdf/, PROMPT.md), the .zip of the AI applied at once (backup, created on the template, updated, a report),
its reponse.json alone accepted, a branch of existing concepts asks for pivots, a frozen brick left out and refused, the rights.
On the Rover of DEMO."""
import io
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core import auth, db, modules, router, startup  # noqa: E402
from core.config import load_config  # noqa: E402
from tests.test_diamond_concept_cards import png, zipped  # noqa: E402
from tools.api_client import ApiFailure, Client  # noqa: E402


class ConceptRoundTest(unittest.TestCase):
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
        url = "http://127.0.0.1:{}".format(cls.server.server_address[1])
        cls.admin = Client(url)
        cls.admin.login("admin", "admin")
        cls.pid = next(p["id"] for p in cls.admin.get("/api/me")["projects"] if p["key"] == "DEMO")
        cls.base = "/api/diamond/p/{}".format(cls.pid)
        made = cls.admin.post("/api/admin/users", {"username": "lecteur", "display_name": "Lecteur"})
        cls.admin.put("/api/admin/projects/{}/members/{}".format(cls.pid, made["user"]["id"]), {"role": "reader"})
        cls.reader = Client(url)
        cls.reader.login("lecteur", made["temp_password"], new_password="Lecture-2026!")
        cls.all = cls.admin.get(cls.base + "/concepts/round?fid=all")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def _branch(self, to_define):
        return next(b for b in self.all["branches"] if b["bricks"] and (b["to_define"] > 0) == to_define)

    def _bricks(self):
        return {c["code"]: c for c in self.admin.get(self.base + "/concepts")["concepts"]}

    def _sheets(self, code):
        return {s["code"]: s for s in self.admin.get(self.base + "/sheets")["sheets"] if s["code"].startswith(code + ".")}

    def _import(self, data, who=None):
        return (who or self.admin).upload(self.base + "/concepts/round/import", data, "application/zip", "ia.zip")

    def test_01_all_branches_prompt(self):
        r = self.all
        self.assertGreater(len(r["branches"]), 2)
        self.assertEqual(r["scope"], "toutes les branches")
        for text in ("un seul fichier .zip", "reponse.json", "prochain code libre", "garde **son code exact**", '"badge"', '"questions"'):
            self.assertIn(text, r["prompt"])
        self.assertNotIn("Cold plate sous les cells", r["prompt"])  # no example from another product
        self.assertEqual(self.reader.get(self.base + "/concepts/round?fid=all")["prompt"], r["prompt"])  # a reader may prepare too

    def test_02_branch_of_existing_concepts_asks_for_pivots(self):
        b = self._branch(False)
        r = self.admin.get(self.base + "/concepts/round?fid={}".format(b["id"]))
        self.assertIn("pivot", r["prompt"])
        self.assertIn("F{}".format(b["label"].split()[0][1:]), r["scope"])
        with self.assertRaises(ApiFailure) as caught:
            self.admin.get(self.base + "/concepts/round?fid=999999")
        self.assertEqual(caught.exception.status, 400)

    def test_03_round_trip_create_update_context(self):
        b = self._branch(True)
        r = self.admin.get(self.base + "/concepts/round?fid={}".format(b["id"]))
        brick = next(c for c in self._bricks().values() if c["code"] in r["prompt"] and c["kind"] == "to_define" and not c["frozen"])
        n, first = brick["number"], "CB-{}.".format(brick["number"])
        start = len(self._sheets(brick["code"]))
        code_a, code_b = "CB-{}.{}".format(n, 50), "CB-{}.{}".format(n, 51)
        answer = {"sheets": [{"code": c, "concept": brick["code"], "kind": "ai", "status": "open", "title": "Idée " + c,
                              "principle": "Principe " + c, "description": "D", "pros": "léger", "cons": "fragile",
                              "questions": "durée de vie ?", "badge": "sans outil", "image": "images/{}_croquis.png".format(c)}
                             for c in (code_a, code_b)]}
        data = zipped({"reponse.json": json.dumps(answer, ensure_ascii=False).encode(),
                       "images/{}_croquis.png".format(code_a): png(4, 3, (200, 10, 10)),
                       "images/{}_croquis.png".format(code_b): png(4, 3, (10, 200, 10)),
                       "pdf/{}_croquis.pdf".format(code_a): b"%PDF-1.4\n%%EOF\n"})
        done = self._import(data)  # applied at once, no preview
        self.assertTrue(done["imported"])
        self.assertEqual((done["created"], done["updated"]), (2, 0))
        self.assertTrue(done["backup"])
        sheets = self._sheets(brick["code"])
        self.assertEqual(len(sheets), start + 2)
        a = sheets[code_a]
        self.assertEqual((a["kind"], a["badge"], a["questions"]), ("ai", "sans outil", "durée de vie ?"))
        self.assertTrue(a["figure_id"] and a["pdf_id"])
        self.assertFalse(a["attachment_id"])  # drawn on the template
        again = self._import(data)  # the same .zip twice: a report, not an error
        self.assertFalse(again["imported"])
        self.assertEqual(again["counts"]["exists"], 2)
        # the next round: the context .zip carries the sketches; the AI changes one sheet, keeps its code
        r = self.admin.get(self.base + "/concepts/round?fid={}".format(b["id"]))
        self.assertIn("feuille " + code_a, r["prompt"])
        self.assertIn("prochain code libre : CB-{}.52".format(n), r["prompt"])
        self.assertIn("fichier de contexte joint", r["prompt"])
        status, headers, body = self.admin.raw_get(self.base + "/concepts/round/context.zip?fid={}".format(b["id"]))
        z = zipfile.ZipFile(io.BytesIO(body))
        names = z.namelist()
        self.assertIn("contexte.json", names)
        self.assertIn("PROMPT.md", names)
        self.assertTrue(any(x.startswith("images/" + code_a + "_") for x in names), names)
        self.assertTrue(any(x.startswith("pdf/" + code_a + "_") for x in names), names)
        ctx = json.loads(z.read("contexte.json"))
        self.assertIn(code_b, [s["code"] for s in ctx["sheets"]])
        changed = {"sheets": [dict(answer["sheets"][1], principle="Nouveau principe", image="")]}
        done = self._import(json.dumps(changed).encode())  # the reponse.json alone (an assistant without files)
        self.assertEqual((done["created"], done["updated"]), (0, 1))
        self.assertEqual(self._sheets(brick["code"])[code_b]["principle"], "Nouveau principe")
        self.assertEqual(len(self._sheets(brick["code"])), start + 2)  # updated, not duplicated
        self.assertTrue(first)

    def test_04_frozen_brick_left_out_and_refused(self):
        b = self._branch(True)
        bricks = self._bricks()
        r = self.admin.get(self.base + "/concepts/round?fid={}".format(b["id"]))
        target = next(c for c in bricks.values() if c["code"] in r["prompt"] and c["kind"] == "to_define" and not c["frozen"])
        self.admin.post(self.base + "/concepts/{}/freeze".format(target["id"]), {"text": "Retenu en CDR"})
        try:
            r = self.admin.get(self.base + "/concepts/round?fid=all")
            self.assertIn("figées, laissées de côté : ", r["prompt"])
            self.assertIn(target["code"], r["frozen"])
            code = "CB-{}.60".format(target["number"])
            data = zipped({"reponse.json": json.dumps({"sheets": [{"code": code, "title": "Pendant le gel"}]}).encode()})
            done = self._import(data)
            line = next(e for e in done["entries"] if e["code"] == code)
            self.assertEqual(line["status"], "refused")
            self.assertIn("figée", line["reason"])
            with self.assertRaises(ApiFailure) as caught:
                self._import(data, self.reader)
            self.assertEqual(caught.exception.status, 403)
        finally:
            self.admin.post(self.base + "/concepts/{}/unfreeze".format(target["id"]), {"reason": "fin de l'essai"})


if __name__ == "__main__":
    unittest.main()
