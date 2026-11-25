"""Diamond · the groups of competencies (0.60.119, D-O-132; since 0.60.130, D-O-143, a filter of the display only). The sets of columns a
kind of product needs -- mechatronics, electronics and power, embedded software, mechanics and structure, battery and energy
storage, regulated product, industrialisation. The page shows one group at a time, or everything (« Toutes / All »); nothing is
written, no rating is ever erased by changing the group (static/js/diamond/competency_profiles.js).
"""
from . import competencies as CP

# (key, name, what it is for, codes in the order of the grid) -- every code is in the default catalogue (data_competencies.py)
PROFILES = [
    ("mechatronics", "Mécatronique", "Un produit qui bouge, mesure et se pilote : la base d'une équipe d'ingénierie.",
     ("MECH", "PCB", "FW", "PWR", "TEST")),
    ("electronics", "Électronique et puissance", "Cartes, conversion d'énergie, faisceaux et leur thermique.",
     ("PCB", "PWR", "HARN", "THERM", "TEST")),
    ("software", "Logiciel embarqué", "Le produit est surtout du firmware et son architecture.",
     ("FW", "SYS", "PCB", "TEST")),
    ("mechanics", "Mécanique et structure", "Pièces, tenue mécanique, thermique et fabrication.",
     ("MECH", "FEA", "THERM", "MFG", "TEST")),
    ("energy", "Batterie et stockage d'énergie", "Cellules, modules, puissance et sécurité des personnes.",
     ("CELL", "PWR", "THERM", "SAFE", "TEST")),
    ("regulated", "Produit réglementé", "Un produit à certifier : sécurité (TR), conformité et qualité en plus de la base.",
     ("MECH", "PCB", "FW", "SAFE", "CERT", "QUAL", "TEST")),
    ("industrial", "Industrialisation", "Passer du prototype à la série : fabrication, procédés spéciaux, contrôle.",
     ("MECH", "MFG", "SPEC", "QUAL", "TEST")),
]


def profiles(conn):
    """[{key, name, summary, codes}] -- the codes still active in the catalogue."""
    active = {c["code"] for c in CP.catalog(conn, active_only=True)}
    return [{"key": key, "name": name, "summary": summary, "codes": [c for c in codes if c in active]}
            for key, name, summary, codes in PROFILES]
