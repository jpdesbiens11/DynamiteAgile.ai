"""Diamond · « ↔ IA » without duplicates (0.60.135, D-O-148).

An assistant often loses the codes on the way: it gives back an existing function, brick or risk without its code (or with a « +… »
temporary code), and the import used to read it as a removal (the code absent from the answer) plus a creation (an item without a
code) -- a duplicate, or an artefact whose links and history were lost. Each section names what identifies an item besides its
code (DUP: a function by its text and its parent, a brick by its name, a DFMEA row by its function, failure mode and cause…); a new
item of the answer that repeats one of the Space, case, accents and punctuation aside:
  - takes back the code of an item ABSENT from the answer: the line is the update (or « Identique ») of that item, never a
    removal and a creation; a « +… » code that other new items point to now names that item;
  - repeats an item still PRESENT in the answer, or a new item earlier in the same answer: the line stays « Nouveau » but starts
    unticked, with the reason; the team ticks it when it really is another item.
"""
import re
import unicodedata

DUP = {
    "story": ("title",), "functions": ("text", "parent"), "ports": ("label", "side"), "parts": ("name",),
    "flows": ("view", "kind", "src", "dst"), "concepts": ("name",), "pugh": ("title",), "risks": ("title",),
    "dfmea": ("function", "failure_mode", "cause"), "chars": ("label", "part"), "process_lines": ("name",),
    "process_ops": ("line", "op"), "pfmea": ("operation", "failure_mode", "cause"), "cplans": ("title",),
    "cplan_items": ("plan", "operation", "characteristic", "char_label"), "costs_nre": ("title",), "costs_lines": ("part", "name"),
}
WORDS = {"title": "titre", "text": "texte", "name": "nom", "label": "libellé", "side": "côté", "view": "vue", "kind": "nature",
         "src": "source", "dst": "destination", "function": "fonction", "part": "pièce", "line": "ligne", "op": "numéro d'opération",
         "operation": "opération", "plan": "plan", "characteristic": "caractéristique", "char_label": "caractéristique"}


def norm(value):
    """A value as the duplicate check reads it: case, accents and punctuation aside; a list in any order."""
    if isinstance(value, (list, tuple)):
        return ",".join(sorted(norm(v) for v in value))
    plain = unicodedata.normalize("NFKD", "" if value is None else str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9+]+", " ", plain.lower()).strip()


class Guard:
    """The duplicate check of one section of the answer. value(name, rec): the JSON value of a field of a record of the Space."""

    def __init__(self, sec, current, items, value):
        self.fields = DUP.get(sec.key, ())
        self.what = "même " + ", ".join(WORDS.get(n, n) for n in self.fields)
        self.known, self.fresh, self.claimed = {}, {}, set()
        self.present = {str(it.get("code") or "").strip() for it in items if isinstance(it, dict)}
        names = {f.key for f in sec.fields}
        if not self.fields or not set(self.fields) <= names:
            self.fields = ()
            return
        for code, rec in current.items():
            key = tuple(norm(value(n, rec)) for n in self.fields)
            if key[0]:
                self.known.setdefault(key, []).append(code)

    def check(self, item, n):
        """(code taken back, reason to untick) of a new item of the answer (no code, or a « +… » one); (None, "") otherwise."""
        if not self.fields:
            return None, ""
        key = tuple(norm(item.get(name)) for name in self.fields)
        if not key[0]:
            return None, ""
        codes = self.known.get(key, [])
        back = next((c for c in codes if c not in self.present and c not in self.claimed), None)
        if back:
            self.claimed.add(back)
            return back, ""
        if codes:
            return None, ("Doublon probable de {} ({}), qui reste dans la réponse : décoché. Correctif : gardez le code {} pour le "
                          "modifier, ou cochez la ligne si c'est bien un autre élément.".format(codes[0], self.what, codes[0]))
        if key in self.fresh:
            return None, ("Doublon probable de l'élément n° {} de la réponse, « {} » ({}) : décoché. Correctif : cochez la ligne si "
                          "c'est bien un autre élément.".format(*self.fresh[key], self.what))
        self.fresh[key] = (n, str(item.get(self.fields[0]))[:60])
        return None, ""

    def note(self, code, temp):
        return "Code retrouvé : {}{} rendu sans son code, reconnu ({}) ; il est mis à jour, pas recréé.".format(
            code, " (« {} » dans la réponse)".format(temp) if temp else "", self.what)
