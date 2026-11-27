"""0.60.131 (D-O-144): Diamond -- « Importer un lot (.zip) » reads the reponse.json of the .zip ({"sheets": [...]}, the answer of
« ↔ IA ») with images/<code>_schema.png: new codes (CB-n.6 … CB-n.10) create five « ai » sheets with all their text, their sketch
drawn on the template (figure_id), CB-n.9 before CB-n.10; the same .zip with existing codes updates the sheets, no duplicate, then
« Déjà là »; optional « questions » and « badge »; a per-sheet report; a sheet turned into a Scan by the earlier import is repaired."""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core import auth, db, modules, router, startup  # noqa: E402
from core.config import load_config  # noqa: E402
from modules.diamond import concept_cards_json as J  # noqa: E402
from tests.test_diamond_concept_cards import png, zipped  # noqa: E402
from tools.api_client import ApiFailure, Client  # noqa: E402

NEW = ["6", "7", "8", "9", "10"]


def answer(n, numbers, extra=None, title="Schéma {}"):
    sheets = []
    for m in numbers:
        code = "CB-{}.{}".format(n, m)
        sheet = {"code": code, "concept": "CB-{}".format(n), "kind": "ai", "status": "open", "title": title.format(code),
                 "principle": "Principe " + code, "description": "Description " + code, "pros": "léger\nsans outil",
                 "cons": ["fragile"], "image": "images/{}_schema.png".format(code)}
        sheet.update(extra or {})
        sheets.append(sheet)
    files = {"reponse.json": json.dumps({"sheets": sheets}, ensure_ascii=False).encode("utf-8")}
    for i, m in enumerate(numbers):
        files["images/CB-{}.{}_schema.png".format(n, m)] = png(3 + i, 2, (20 * i, 90, 160))
    return zipped(files)


class SheetsJsonImportTest(unittest.TestCase):
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
        cls.base = "/api/diamond/p/{}".format(cls.pid)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def _brick(self, name, sheets=0):
        data = self.admin.post(self.base + "/concepts", {"name": name, "kind": "to_define"})
        brick = next(c for c in data["concepts"] if c["id"] == data["created"])
        for i in range(sheets):
            self.admin.post(self.base + "/concepts/{}/sheets".format(brick["id"]), {"title": "Feuille {}".format(i + 1), "kind": "ai"})
        return brick

    def _sheets(self, brick):
        return {s["code"]: s for s in self.admin.get(self.base + "/concepts/{}".format(brick["id"]))["sheets"]}

    def _import(self, data, mode):
        return self.admin.upload(self.base + "/sheets/import?mode=" + mode, data, "application/zip", "lot.zip")

    def test_01_code_key_is_numeric(self):
        self.assertEqual(sorted(["CB-6.10", "CB-6.1", "CB-6.9", "CB-10.1", "CB-6.2"], key=J.code_key),
                         ["CB-6.1", "CB-6.2", "CB-6.9", "CB-6.10", "CB-10.1"])

    def test_02_new_codes_create_ai_sheets_on_the_template(self):
        brick = self._brick("Châssis du rover", sheets=5)  # CB-n.1 … CB-n.5 exist, like CB-6 of the report
        n = brick["number"]
        data = answer(n, NEW, title="Schema")  # the same title five times: five sheets all the same (codes, not titles)
        prev = self._import(data, "preview")
        self.assertEqual(prev["counts"], {"new": 5, "update": 0, "attach": 0, "exists": 0, "refused": 0}, prev)
        self.assertEqual([e["code"] for e in prev["entries"]], ["CB-{}.{}".format(n, m) for m in NEW])  # 9 before 10
        self.assertEqual({e["kind"] for e in prev["entries"]}, {"ai"})
        self.assertFalse(any("Scan" in w or "ignoré" in w for w in prev["warnings"]), prev["warnings"])
        done = self._import(data, "apply")
        self.assertEqual((done["created"], done["updated"]), (5, 0))
        self.assertTrue(all(e["outcome"].startswith("créée CB-") for e in done["entries"]), done["entries"])
        sheets = self._sheets(brick)
        self.assertEqual(len(sheets), 10)
        last = sheets["CB-{}.10".format(n)]
        self.assertEqual((last["kind"], last["status"], last["title"]), ("ai", "open", "Schema"))
        self.assertEqual((last["principle"], last["cons"]), ("Principe CB-{}.10".format(n), "fragile"))
        self.assertEqual(last["pros"], "léger\nsans outil")
        self.assertTrue(last["figure_id"])
        self.assertFalse(last["attachment_id"])  # not a raw picture: drawn on the template
        status, headers, svg = self.admin.raw_get(self.base + "/sheets/{}/sheet.svg".format(last["id"]))
        text = svg.decode("utf-8")
        self.assertIn("Concept sheet CB-{}.10".format(n), text)
        self.assertIn("data:image/png;base64,", text)  # the sketch in the drawing area
        self.assertIn("fragile", text)

    def test_03_existing_codes_are_updated_not_duplicated(self):
        brick = self._brick("Roues du rover")
        n = brick["number"]
        self._import(answer(n, ["1", "2"]), "apply")
        again = self._import(answer(n, ["1", "2"]), "preview")
        self.assertEqual(again["counts"]["exists"], 2)  # the same .zip twice: nothing to do, said
        changed = answer(n, ["1", "2"], extra={"principle": "Nouveau principe", "questions": ["couple ?", "masse ?"],
                                               "badge": "tout terrain"})
        prev = self._import(changed, "preview")
        self.assertEqual(prev["counts"]["update"], 2, prev)
        self.assertIn("principle", prev["entries"][0]["changes"])
        done = self._import(changed, "apply")
        self.assertEqual((done["created"], done["updated"]), (0, 2))
        sheets = self._sheets(brick)
        self.assertEqual(len(sheets), 2)  # no duplicate
        one = sheets["CB-{}.1".format(n)]
        self.assertEqual((one["principle"], one["badge"], one["questions"]), ("Nouveau principe", "tout terrain", "couple ?\nmasse ?"))
        status, headers, svg = self.admin.raw_get(self.base + "/sheets/{}/sheet.svg".format(one["id"]))
        self.assertIn("tout terrain", svg.decode("utf-8"))

    def test_04_a_scan_left_by_the_old_import_is_repaired(self):
        brick = self._brick("Mât du rover")
        n = brick["number"]
        code = "CB-{}.10".format(n)
        self._import(zipped({"images/{}_schema.png".format(code): png(2, 2, (1, 2, 3))}), "apply")  # what 0.60.130 did
        scan = self._sheets(brick)[code]
        self.assertEqual((scan["kind"], scan["title"]), ("scan", "Schema"))
        done = self._import(answer(n, ["10"]), "apply")
        self.assertEqual(done["updated"], 1)
        fixed = self._sheets(brick)[code]
        self.assertEqual((fixed["id"], fixed["kind"], fixed["title"]), (scan["id"], "ai", "Schéma " + code))
        self.assertTrue(fixed["figure_id"])
        self.assertFalse(fixed["attachment_id"])

    def test_05_errors_are_lines_not_silence(self):
        brick = self._brick("Antenne du rover")
        n = brick["number"]
        bad = {"sheets": [{"code": "CB-{}.1".format(n), "concept": "CB-999", "title": "x"},
                          {"code": "CB-{}.2".format(n), "title": "Sans image", "image": "images/absente.png"},
                          {"code": "CB-{}.3".format(n), "title": ""}, {"concept": "CB-{}".format(n), "title": "Sans code"}]}
        prev = self._import(zipped({"reponse.json": json.dumps(bad).encode()}), "preview")
        lines = {e["code"] or e["title"]: e for e in prev["entries"]}
        self.assertEqual(lines["CB-{}.1".format(n)]["status"], "refused")
        self.assertIn("même brique", lines["CB-{}.1".format(n)]["reason"])
        self.assertEqual(lines["CB-{}.3".format(n)]["status"], "refused")
        self.assertEqual(lines["CB-{}.2".format(n)]["status"], "new")
        self.assertIn("absente.png", lines["CB-{}.2".format(n)]["warning"])
        self.assertEqual(lines["Sans code"]["status"], "new")
        with self.assertRaises(ApiFailure) as caught:  # nothing to read: the reason is in the message
            self._import(zipped({"reponse.json": b'{"concepts": [{"name": "x"}], "sheets": []}'}), "preview")
        self.assertIn("concepts", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
