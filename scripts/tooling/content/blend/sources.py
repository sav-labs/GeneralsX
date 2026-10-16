"""Specs for the detailed units built from third-party source models (build_src.py).

GeneralsX @feature Claude 16/10/2026 Per unit: the game model it replaces, texture stem, game length
(+X forward), yaw to turn the source to face +X, triangle budget, bone parents, rules that sort the
source's pieces onto bones (see import_src.classify), and burn marks for the damaged bake. Rules are
written against each source after inspecting its object names; credits live in fetch/picks.txt and
the CREDITS.md fetched with the sources.
"""

UNITS = {
    # M1A1 Abrams by MirzaArrafiERV_45, CC-BY. Its objects are split by material, so the turret, gun and
    # wheels are picked out of the loose pieces by position; misc_a.4 is a decal layer (alpha-cut
    # markings) and is dropped; the track keeps the source's links for now (static).
    "crusader": {
        "model": "AVGXMBT", "stem": "gxmbt3", "length": 45.0, "yaw": 90.0, "tris": 16000, "split": ".",
        "parents": {"BARREL": "TURRET"},
        "rules": [
            {"name": r"misc_a\.4", "bone": "DROP"},
            {"box": (4.0, 30.0, -1.2, 1.2, 8.3, 11.0), "bone": "BARREL"},
            {"box": (-17.0, 6.0, -8.0, 8.0, 7.9, 30.0), "bone": "TURRET"},
            # Road wheels (centres 2 up, 6.2 out), drive sprocket at the rear, idler at the front; the
            # torsion-bar arms just inboard stay on the hull.
            {"box": (-16.0, 9.0, 5.6, 7.0, 1.2, 2.8), "maxsize": 4.0, "bone": "WHEEL#"},
            {"box": (-16.0, 9.0, -7.0, -5.6, 1.2, 2.8), "maxsize": 4.0, "bone": "WHEEL#"},
            {"box": (-20.0, -16.5, 4.8, 7.2, 3.6, 5.4), "maxsize": 4.0, "bone": "SPROCKET#"},
            {"box": (-20.0, -16.5, -7.2, -4.8, 3.6, 5.4), "maxsize": 4.0, "bone": "SPROCKET#"},
            {"box": (11.0, 14.0, 4.0, 6.0, 3.6, 5.6), "maxsize": 4.0, "bone": "IDLER#"},
            {"box": (11.0, 14.0, -6.0, -4.0, 3.6, 5.6), "maxsize": 4.0, "bone": "IDLER#"},
        ],
        # Desert tan over the source's grey-olive: (colour, the source's mean luminance, how much).
        "tint": ((176, 156, 112), 0.3, 0.85),
        "burns": [((-15.0, 0.0, 7.0), 9.0), ((-3.0, 6.5, 10.0), 6.0), ((2.0, -7.0, 5.0), 6.0), ((-9.0, 7.5, 5.0), 5.0),
                  ((8.0, 2.0, 8.0), 4.0)],
    },
    "test": {
        "model": "AVGXTEST", "stem": "gxtest", "length": 31.0, "yaw": 0.0, "tris": 15000, "split": r"^WHEEL",
        "parents": {"BARREL": "TURRET", "WHEEL#": "ROOTTRANSFORM"},
        "rules": [
            {"name": r"^BARREL|GUN", "bone": "BARREL"},
            {"name": r"^TURRET|HOUSECOLOR01", "bone": "TURRET"},
            {"name": r"TREADS", "bone": "ROOTTRANSFORM", "group": "TREADS", "kind": "tread"},
            {"name": r"^WHEEL", "bone": "WHEEL#"},
        ],
        "burns": [((-11.5, 0.0, 5.6), 5.5), ((-1.4, 6.5, 7.2), 2.7)],
    },
}
