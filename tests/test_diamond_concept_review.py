"""0.60.133 (D-O-146): Diamond -- « Revue » of the concept sheets: keep (seen, by whom), drop (« Dropped », seen), reopen (« Open »,
not seen), shared by the team through the list of the sheets; a sheet retained by a Pugh matrix is not dropped; a frozen brick takes
no review; a reader may not review; an unknown action is refused. On the Rover of DEMO."""
import sys
import tempfile
import threading
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core import auth, db, modules, router, startup  # noqa: E402
from core.config import load_config  # noqa: E402
from tools.api_client import ApiFailure, Client  # noqa: E402


class ConceptReviewTest(unittest.TestCase):
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
        data = cls.admin.post(cls.base + "/concepts", {"name": "Brique de revue", "kind": "to_define"})
        cls.brick = next(c for c in data["concepts"] if c["id"] == data["created"])
        url = cls.base + "/concepts/{}/sheets".format(cls.brick["id"])
        cls.sheets = []
        for title in ("Première", "Deuxième", "Troisième"):
            made = cls.admin.post(url, {"title": title, "kind": "ai"})
            cls.sheets.append(next(s for s in made["sheets"] if s["id"] == made["created"]))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def fails(self, status, fn, *args):
        with self.assertRaises(ApiFailure) as caught:
            fn(*args)
        self.assertEqual(caught.exception.status, status, caught.exception)

    def _review(self, sheet, action, who=None):
        return (who or self.admin).post(self.base + "/sheets/{}/review".format(sheet["id"]), {"action": action})["sheet"]

    def test_01_keep_drop_reopen(self):
        a, b = self.sheets[0], self.sheets[1]
        kept = self._review(a, "keep")
        self.assertTrue(kept["reviewed_at"])
        self.assertEqual((kept["status"], kept["reviewer_name"]), ("open", "Administrateur"))
        dropped = self._review(b, "drop")
        self.assertEqual(dropped["status"], "dropped")
        self.assertTrue(dropped["reviewed_at"])
        listed = {s["id"]: s for s in self.reader.get(self.base + "/sheets")["sheets"]}  # shared: a reader sees who saw what
        self.assertTrue(listed[a["id"]]["reviewed_at"])
        self.assertEqual(listed[b["id"]]["status"], "dropped")
        back = self._review(b, "reopen")
        self.assertEqual((back["status"], back["reviewed_at"]), ("open", None))
        self._review(b, "drop")
        again = self._review(b, "keep")  # 0.60.134 (D-O-147): keep on a dropped sheet = back in the running, seen
        self.assertEqual(again["status"], "open")
        self.assertTrue(again["reviewed_at"])

    def test_02_refusals(self):
        c = self.sheets[2]
        self.fails(400, self.admin.post, self.base + "/sheets/{}/review".format(c["id"]), {"action": "zap"})
        self.fails(403, self._review, c, "keep", self.reader)
        with db.connect() as conn:  # retained by a Pugh matrix
            conn.execute("UPDATE diamond_concept_sheets SET status = 'selected' WHERE id = ?", (c["id"],))
        try:
            self.fails(409, self._review, c, "drop")
            self.assertEqual(self._review(c, "keep")["status"], "selected")  # keep stays possible
        finally:
            with db.connect() as conn:
                conn.execute("UPDATE diamond_concept_sheets SET status = 'open' WHERE id = ?", (c["id"],))
        self.admin.post(self.base + "/concepts/{}/freeze".format(self.brick["id"]), {"text": "Retenu"})
        try:
            self.fails(409, self._review, c, "keep")
        finally:
            self.admin.post(self.base + "/concepts/{}/unfreeze".format(self.brick["id"]), {"reason": "fin"})

    def test_03_compact_card_details_on_double_click(self):
        """0.60.136 (D-O-149): the card shows code and badges, title, the sheet as a thumbnail, principle and every button; the
        description, + / − / ? and author are one double-click (or Entrée, or « Détails ») away: « ▶ Revue » on this sheet, its brick."""
        js = (BASE_DIR / "static/js/diamond/concept_sheets.js").read_text("utf-8")
        card = js[js.index("  function card("):js.index("  function sheetSection(")]
        for text in ('"0.60.136-sheet-compact"', '"dblclick"', 'ev.key === "Enter"', '{ scope: "c" + s.concept_id, id: s.id, filter: "all" }',
                     "{ thumb: true }", '"Détails"', '"Modifier"', "Raffiner avec l'IA", '"Archiver"', '"Supprimer"', "s.principle"):
            self.assertIn(text, card)
        for hidden in ("s.description", "s.pros", "s.cons", "s.questions", "author_name"):
            self.assertNotIn(hidden, card)
        review = (BASE_DIR / "static/js/diamond/concept_review.js").read_text("utf-8")
        self.assertIn("(start && start.filter)", review)
        self.assertIn("R raffiner avec l'IA", review)


if __name__ == "__main__":
    unittest.main()
