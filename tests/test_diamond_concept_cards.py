"""0.60.125 (D-O-138): Diamond -- concept sheets by batch and on the platform's template: a .zip of cards (.md) with the picture
and the PDF of each sheet (preview, then import; the number CB-n.m kept when free; a second import creates nothing), the sheet drawn
on its template as SVG and PDF (badge, + / − / ?, title block; the figure placed in the drawing area), the prompt of one branch of
the tree for the AI, the rights. On the Rover of DEMO."""
import base64
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
from modules.diamond import concept_cards  # noqa: E402
from tools.api_client import ApiFailure, Client  # noqa: E402

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
CARDS = """# CB-{n} — cartes à créer
Format : Titre / Principle / Description / + / − / ?

## CB-{n}.7 — Bras articulé à ressort compensé
**Principle:** Un ressort équilibre le poids de la tête : elle reste où on la lâche.
Deux bras en parallélogramme ; ressort de traction réglé en usine.
+ aucun réglage de vis ; geste naturel
+ tête toujours parallèle au plan de travail
− fatigue du ressort
? durée de vie (n ≥ 10 000 cycles)
**Badge:** sans outil

## CB-{n}.8 — Col de cygne en tube spiralé
**Principle:** Un tube métallique spiralé garde la forme qu'on lui donne.
+ très bas coût
− retour élastique après de nombreux pliages
"""


def make_zip(n):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("lot/cartes.md", CARDS.format(n=n))
        z.writestr("lot/CB-{}.7_bras_ressort.png".format(n), PNG)
        z.writestr("lot/CB-{}.7_bras_ressort.pdf".format(n), PDF)
        z.writestr("lot/CB-{}.9_pince_etau.png".format(n), PNG)  # a picture without its card: a sheet of its own
        z.writestr("lot/CB-{}_synthese.png".format(n), PNG)  # the brick only: imported with extras=1, with its PDF
        z.writestr("lot/CB-{}_synthese.pdf".format(n), PDF)
        z.writestr("lot/CB-{0}.7-{0}.8_brainwriting.pdf".format(n), PDF)  # a range: the brick's, not CB-n.7's
        z.writestr("lot/notes.docx", b"ignored")
    return buf.getvalue()


class ConceptCardsTest(unittest.TestCase):
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
        cls.url = "http://127.0.0.1:{}".format(cls.server.server_address[1])
        cls.admin = Client(cls.url)
        cls.admin.login("admin", "admin")
        cls.pid = next(p["id"] for p in cls.admin.get("/api/me")["projects"] if p["key"] == "DEMO")
        cls.base = "/api/diamond/p/{}".format(cls.pid)
        made = cls.admin.post("/api/admin/users", {"username": "lecteur", "display_name": "Lecteur"})
        cls.admin.put("/api/admin/projects/{}/members/{}".format(cls.pid, made["user"]["id"]), {"role": "reader"})
        cls.reader = Client(cls.url)
        cls.reader.login("lecteur", made["temp_password"], new_password="Lecture-2026!")
        data = cls.admin.post(cls.base + "/concepts", {"name": "Bras de la lampe", "initial_name": "Bras libre", "kind": "to_define"})
        cls.brick = next(c for c in data["concepts"] if c["id"] == data["created"])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def fails(self, status, fn, *args):
        with self.assertRaises(ApiFailure) as caught:
            fn(*args)
        self.assertEqual(caught.exception.status, status, caught.exception)

    def test_01_parse_cards(self):
        cards = concept_cards.parse_cards(CARDS.format(n=4))
        self.assertEqual([c["code"] for c in cards], ["CB-4.7", "CB-4.8"])
        a = cards[0]
        self.assertEqual((a["brick"], a["number"], a["badge"]), (4, 7, "sans outil"))
        self.assertTrue(a["principle"].startswith("Un ressort"))
        self.assertEqual(a["pros"].count("\n"), 1)
        self.assertIn("fatigue", a["cons"])
        self.assertIn("10 000", a["questions"])
        self.assertIn("parallélogramme", a["description"])

    def test_02_zip_preview_then_import(self):
        n = self.brick["number"]
        data = make_zip(n)
        url = self.base + "/sheets/import?mode=preview"
        prev = self.admin.upload(url, data, "application/zip", "lot.zip")
        self.assertEqual(prev["counts"], {"new": 3, "exists": 0, "refused": 0})
        self.assertEqual(sorted(prev["left"]), sorted(["CB-{}_synthese.png".format(n), "CB-{}_synthese.pdf".format(n),
                                                        "CB-{0}.7-{0}.8_brainwriting.pdf".format(n)]))
        arm = next(e for e in prev["entries"] if e["code"] == "CB-{}.7".format(n))
        self.assertEqual(len(arm["files"]), 2)
        self.assertEqual(self.admin.get(self.base + "/concepts/{}".format(self.brick["id"]))["sheets"], [])  # preview builds nothing
        done = self.admin.upload(self.base + "/sheets/import?mode=apply&extras=1", data, "application/zip", "lot.zip")
        self.assertEqual(done["created"], 5)  # 3 sheets, the synthesis (picture + PDF), the brainwriting
        sheets = {s["code"]: s for s in self.admin.get(self.base + "/concepts/{}".format(self.brick["id"]))["sheets"]}
        arm = sheets["CB-{}.7".format(n)]
        self.assertEqual((arm["kind"], arm["badge"], arm["file_mime"]), ("ai", "sans outil", "image/png"))
        self.assertTrue(arm["pdf_id"])
        self.assertIn("CB-{}.8".format(n), sheets)
        self.assertEqual(sheets["CB-{}.9".format(n)]["kind"], "scan")
        self.assertEqual(len(sheets), 5)  # the synthesis and the brainwriting took the next free numbers
        synth = next(s for s in sheets.values() if s["title"] == "Synthese")
        self.assertEqual((synth["file_mime"], bool(synth["pdf_id"])), ("image/png", True))
        status, headers, body = self.admin.raw_get(self.base + "/sheets/{}/file?which=pdf".format(arm["id"]))
        self.assertTrue(body.startswith(b"%PDF"))
        again = self.admin.upload(self.base + "/sheets/import?mode=preview&extras=1", data, "application/zip", "lot.zip")
        self.assertEqual(again["counts"]["new"], 0)  # the same .zip twice: nothing new
        self.fails(409, self.admin.upload, self.base + "/sheets/import?mode=apply&extras=1", data, "application/zip", "lot.zip")

    def test_03_target_brick_and_refusals(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("c.md", "## CB-999.1 — Pied lesté\n**Principle:** Un socle en fonte.\n+ stable\n")
        prev = self.admin.upload(self.base + "/sheets/import", buf.getvalue(), "application/zip", "c.zip")
        self.assertEqual(prev["counts"]["refused"], 1)
        prev = self.admin.upload(self.base + "/sheets/import?cid={}".format(self.brick["id"]), buf.getvalue(), "application/zip", "c.zip")
        self.assertEqual(prev["counts"]["new"], 1)
        self.fails(415, self.admin.upload, self.base + "/sheets/import", b"not a zip", "application/zip", "x.zip")
        self.fails(403, self.reader.upload, self.base + "/sheets/import", buf.getvalue(), "application/zip", "c.zip")

    def test_04_sheet_on_template(self):
        up = self.admin.upload(self.base + "/sheets/upload", PNG, "image/png", "croquis.png")
        made = self.admin.post(self.base + "/concepts/{}/sheets".format(self.brick["id"]), {
            "title": "Lampe à pince <étau>", "principle": "Une pince serre le plateau.", "pros": "+ se pose partout\nrapide",
            "cons": "− marque le bois", "questions": "? épaisseur maximale", "badge": "sans outil", "figure_id": up["id"]})
        sheet = next(s for s in made["sheets"] if s["id"] == made["created"])
        self.assertEqual(sheet["kind"], "digital")  # a drawing in the template is not a scan
        status, headers, svg = self.admin.raw_get(self.base + "/sheets/{}/sheet.svg".format(sheet["id"]))
        text = svg.decode("utf-8")
        self.assertIn("Concept sheet " + sheet["code"], text)
        self.assertIn("&lt;étau&gt;", text)  # escaped
        self.assertIn("sans outil", text)
        self.assertIn("data:image/png;base64,", text)
        self.assertNotIn("<script", text)
        status, headers, pdf = self.reader.raw_get(self.base + "/sheets/{}/sheet.pdf".format(sheet["id"]))
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertIn(b"/Im1", pdf)
        self.fails(400, self.admin.patch, self.base + "/sheets/{}".format(sheet["id"]), {"figure_id": 999999})
        self.admin.patch(self.base + "/sheets/{}".format(sheet["id"]), {"figure_id": None})

    def test_05_branch_prompt(self):
        fns = self.admin.get(self.base + "/concepts")["functions"]
        busy = {fid for c in self.admin.get(self.base + "/concepts")["concepts"] for fid in c["function_ids"]}
        second = next(f for f in fns if f["level"] == 2 and any(g["parent_id"] == f["id"] and g["id"] in busy for g in fns))
        res = self.admin.get(self.base + "/concepts/branch-prompt?fid={}".format(second["id"]))
        self.assertIn("F{}".format(second["number"]), res["prompt"])
        self.assertIn('"badge"', res["prompt"])
        self.assertGreater(res["bricks"], 0)
        self.fails(400, self.admin.get, self.base + "/concepts/branch-prompt?fid=0")


if __name__ == "__main__":
    unittest.main()
