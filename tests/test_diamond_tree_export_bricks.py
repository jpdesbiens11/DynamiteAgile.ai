"""0.60.126 (D-O-139): the export of « Arbre fonctionnel » (« Exporter ▾ ») carries the technology bricks and the competencies,
as on the screen: Excel (a « Brique » column, the sheet « Briques technologiques », the sheets of the competencies), draw.io and
PowerPoint (the column of the bricks, linked to their functions). On the Rover of DEMO."""
import io
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
from tools.api_client import Client  # noqa: E402


class TreeExportBricksTest(unittest.TestCase):
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
        cls.bricks = [c for c in cls.admin.get(cls.base + "/concepts")["concepts"] if c["function_ids"]]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def fetch(self, ext):
        status, _h, body = self.admin.raw_get(self.base + "/export.{}?only=tree".format(ext))
        self.assertEqual(status, 200)
        return zipfile.ZipFile(io.BytesIO(body)) if ext != "drawio" else body.decode("utf-8")

    def test_01_excel(self):
        self.assertTrue(self.bricks)
        z = self.fetch("xlsx")
        book = z.read("xl/workbook.xml").decode("utf-8")
        self.assertIn("Arbre fonctionnel", book)
        self.assertIn("Briques technologiques", book)
        self.assertIn("Compétences — par ligne", book)  # the Rover's lines are rated
        text = "".join(z.read(n).decode("utf-8") for n in z.namelist() if n.startswith("xl/") and n.endswith(".xml"))
        first = self.bricks[0]
        self.assertIn(first["code"], text)
        self.assertIn(first["name"].split()[0], text)

    def test_02_drawio(self):
        xml = self.fetch("drawio")
        for c in self.bricks:
            self.assertIn(c["code"], xml)
        self.assertIn("Brique : à définir", xml)

    def test_03_pptx(self):
        z = self.fetch("pptx")
        slides = "".join(z.read(n).decode("utf-8") for n in z.namelist() if n.startswith("ppt/slides/slide"))
        for c in self.bricks:
            self.assertIn(c["code"], slides)


if __name__ == "__main__":
    unittest.main()
