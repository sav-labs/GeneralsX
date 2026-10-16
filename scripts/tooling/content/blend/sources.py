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
    # markings) and is dropped; chassis_vlo.7 is the static track, replaced by our scrolling band.
    "crusader": {
        "model": "AVGXMBT", "stem": "gxmbt3", "length": 45.0, "yaw": 90.0, "tris": 12000, "split": ".",
        "parents": {"BARREL": "TURRET"},
        # The retail Crusader's Draw module fires from TurretMS and recoils Barrel.
        "muzzles": {"TURRETMS": "BARREL", "TURRETFX": "BARREL"},
        "rules": [
            {"name": r"misc_a\.4", "bone": "DROP"},
            {"name": r"chassis_vlo\.7", "bone": "TRACK"},
            {"box": (4.0, 30.0, -1.2, 1.2, 8.3, 11.0), "bone": "BARREL"},
            # The turret with its bustle rack and stowage boxes overhanging the engine deck.
            {"box": (-21.0, 6.0, -8.0, 8.0, 7.9, 30.0), "bone": "TURRET"},
            # Road wheels (centres 2 up, 6.2 out), drive sprocket at the rear, idler at the front; the
            # torsion-bar arms just inboard stay on the hull.
            {"box": (-16.0, 9.0, 5.6, 7.0, 1.2, 2.8), "maxsize": 4.0, "bone": "WHEEL#"},
            {"box": (-16.0, 9.0, -7.0, -5.6, 1.2, 2.8), "maxsize": 4.0, "bone": "WHEEL#"},
            {"box": (-20.0, -16.5, 4.8, 7.2, 3.6, 5.4), "maxsize": 4.0, "bone": "SPROCKET#"},
            {"box": (-20.0, -16.5, -7.2, -4.8, 3.6, 5.4), "maxsize": 4.0, "bone": "SPROCKET#"},
            {"box": (11.0, 14.0, 4.0, 6.0, 3.6, 5.6), "maxsize": 4.0, "bone": "IDLER#"},
            {"box": (11.0, 14.0, -6.0, -4.0, 3.6, 5.6), "maxsize": 4.0, "bone": "IDLER#"},
        ],
        # Desert tan #B49A6E: (colour, unused, how much of the repaint replaces the source's grey-olive).
        "tint": ((180, 154, 110), None, 1.0),
        # Tyres and sprocket teeth: (finish, from what fraction of the wheel's radius outwards).
        "rims": {"WHEEL": ("rubber", 0.8), "SPROCKET": ("metal", 0.82)},
        # Side skirt sections: dark seams between them.
        "seams": [(-25.0, 25.0, 7.4, 9.5, 3.0, 7.5), (-25.0, 25.0, -9.5, -7.4, 3.0, 7.5)],
        "track": {"links": 3.5, "sprocket": 0.88},
        # Damaged: a skirt section torn off on the left, one hanging on the right, the left stowage boxes
        # blown off the turret bustle, the gun sagging.
        "damage": {"drop": [(-10.5, -6.5, 7.4, 9.5, 3.0, 7.5), (-19.5, -14.5, 2.0, 7.5, 9.0, 12.5)],
                   "bend": [((1.0, 7.0, -9.5, -7.4, 3.0, 7.5), 28.0)], "droop": 6.0},
        "burns": [((-15.0, 0.0, 7.0), 6.0), ((-3.0, 6.5, 10.0), 3.5), ((2.0, -7.0, 5.0), 3.5), ((-9.0, 7.5, 5.0), 3.5),
                  ((8.0, 2.0, 8.0), 2.5), ((-5.0, -3.0, 11.5), 2.5), ((-17.0, 4.5, 10.5), 3.0)],
        "fx": {"SMOKE01": (-15.0, -2.0, 7.4), "SMOKE02": (-13.0, 3.0, 7.4), "SMOKE03": (-5.0, 3.0, 11.6),
               "FIRE01": (-15.0, 0.0, 7.4), "FIRE02": (-17.0, -4.5, 7.2), "FIRE03": (-5.0, -3.0, 11.6)},
    },
    # M1A2 Abrams by coderslava402, CC-BY: desert tan with normal and metal/roughness maps. Four objects
    # share the "abram" material (hull, turret floor, turret with its fittings, gun), split into loose
    # faces; "transmin" is one object per wheel, "track" the static track and its upper run, replaced by
    # our scrolling band. The whip antennas would stand 20 units tall and are dropped. In review, not built
    # by CI yet: "crusader" stays the approved M1A1 until this one passes.
    "crusader_m1a2": {
        "model": "AVGXMBT", "stem": "gxmbt3", "length": 45.0, "yaw": 90.0, "tris": 15000, "split": "abram", "weld": 0.002,
        # Its 1K texture is too coarse for the game's close camera: the paint is procedural and the
        # surface detail (plate edges, bolts, welds, hatches) comes from normals and occlusion baked off
        # the full-resolution mesh, with rays reaching 0.25 units either side of the decimated surface.
        "procedural": True, "highpoly": 0.25,
        # CARC Tan 686A as on US Army vehicles today, lightly used: a fleet tank, not a wreck.
        "tint": ((190, 166, 124), None, 1.0), "weathering": 0.35,
        "parents": {"BARREL": "TURRET"},
        # The retail Crusader's Draw module fires from TurretMS and recoils Barrel.
        "muzzles": {"TURRETMS": "BARREL", "TURRETFX": "BARREL"},
        "rules": [
            {"name": r"^Object_13 ", "box": (-18.0, -12.0, -9.0, 9.0, 14.5, 30.0), "bone": "DROP"},
            {"name": r"track", "bone": "TRACK"},
            {"name": r"^Object_9 ", "bone": "BARREL"},
            {"name": r"^Object_(11|13) ", "bone": "TURRET"},
            # Drive sprocket at the rear, idler at the front, seven road wheels between.
            {"name": r"transmin", "box": (-30.0, -16.5, -10.0, 10.0, 0.0, 8.0), "bone": "SPROCKET#"},
            {"name": r"transmin", "box": (8.5, 30.0, -10.0, 10.0, 0.0, 8.0), "bone": "IDLER#"},
            {"name": r"transmin", "bone": "WHEEL#"},
        ],
        "rims": {"WHEEL": ("rubber", 0.8), "SPROCKET": ("metal", 0.82)},
        "track": {"links": 3.5, "sprocket": 0.88},
        # Damaged: the middle skirt section torn off on the left, the rear one hanging on the right, the
        # gun sagging.
        "damage": {"drop": [(-9.9, -3.6, 7.6, 9.2, 2.6, 7.4)],
                   "bend": [((-16.3, -10.1, -9.2, -7.6, 2.6, 7.4), 32.0)], "droop": 6.0},
        "burns": [((-19.0, 0.0, 8.2), 5.0), ((-6.0, 7.6, 10.0), 3.0), ((2.0, -8.4, 5.0), 3.0),
                  ((-7.0, 8.0, 4.5), 3.0), ((4.0, 3.0, 11.0), 2.5), ((-8.0, -3.0, 12.0), 2.5),
                  ((-16.0, 4.5, 11.0), 3.0)],
        # Penetrations: turret side, hull side behind the torn skirt, turret front corner.
        "hits": [((-6.5, 7.7, 10.2), 0.8), ((-6.5, 8.0, 4.6), 0.9), ((3.0, -6.0, 10.0), 0.7)],
        "fx": {"SMOKE01": (-19.0, -2.0, 8.4), "SMOKE02": (-17.0, 3.0, 8.4), "SMOKE03": (-8.0, 3.0, 12.3),
               "FIRE01": (-19.0, 0.0, 8.4), "FIRE02": (-20.0, -4.5, 8.2), "FIRE03": (-8.0, -3.0, 12.3)},
    },
    # M109A6 Paladin by MirzaArrafiERV_45, CC-BY. Named objects: cannon and cradle, turret with its
    # stowage, numbered wheels (1 and 10 the drive sprockets at the front, 9 and 18 the idlers), tracks.
    "paladin": {
        "model": "AVGXPAL", "stem": "gxpal3", "length": 42.0, "yaw": 90.0, "tris": 12000, "split": None,
        "parents": {"BARREL": "TURRET01"},
        # The retail Paladin's Draw module turns Turret01, recoils Barrel and fires from TurretMS.
        "muzzles": {"TURRETMS": "BARREL", "TURRETFX": "BARREL"},
        "rules": [
            {"name": r"^g_cannon", "bone": "BARREL"},
            {"name": r"^g_turret|^g_noeffec|^antenna_short", "bone": "TURRET01"},
            {"name": r"^tread_", "bone": "TRACK"},
            {"name": r"^wheel(1|10)__", "bone": "SPROCKET#"},
            {"name": r"^wheel(9|18)__", "bone": "IDLER#"},
            {"name": r"^wheel\d+__", "bone": "WHEEL#"},
        ],
        "tint": ((180, 154, 110), None, 1.0),
        "rims": {"WHEEL": ("rubber", 0.8), "SPROCKET": ("metal", 0.82)},
        "track": {"links": 3.5, "sprocket": 0.88},
        "damage": {"droop": 5.0},
    },
    # M1126 Stryker by cenobyte, CC-BY, as the Microwave Tank: eight named tyres, the rest stays on the hull.
    "microwave": {
        "model": "AVGXMICRO", "stem": "gxmicro3", "length": 32.0, "yaw": -90.0, "tris": 14000, "split": ".",
        "rules": [{"name": r"^Tyre\d", "bone": "WHEEL#"}],
        "find_wheels": {"zmax": 0.3},
        "tint": ((180, 154, 110), None, 1.0),
        "rims": {"WHEEL": ("rubber", 0.66)},
        "engine": "front",
    },
    # HMMWV M998A1 by 42manako, CC-BY, as the Humvee (canvas top: no gunner yet).
    "humvee": {
        "model": "AVGXJLTV", "stem": "gxjltv3", "length": 22.0, "yaw": 90.0, "tris": 12000, "split": ".",
        "rules": [], "find_wheels": {}, "tires": True,
        "tint": ((180, 154, 110), None, 1.0),
        "rims": {"TIRE": ("rubber", 0.62)},
        "engine": "front",
    },
    # M997A2 ambulance by 42manako, CC-BY. Material_823 is a whip antenna taller than the vehicle.
    "ambulance": {
        "model": "AVGXMEDIC", "stem": "gxmedic3", "length": 24.0, "yaw": 90.0, "tris": 12000, "split": ".",
        "exclude": r"Material_823", "rules": [], "find_wheels": {}, "tires": True,
        "tint": ((180, 154, 110), None, 1.0),
        "rims": {"TIRE": ("rubber", 0.62)},
        "engine": "front",
    },
    # M142 HIMARS by Denys.Cherkasov, CC-BY, as the Tomahawk launcher. The scene also holds a loose
    # missile with a slogan, spare damaged doors and bonnet and tyre valves: excluded. The pod turns
    # on TURRET (the retail Draw module's turret) and launches from its rear end.
    "tomahawk": {
        "model": "AVGXMLRS", "stem": "gxmlrs3", "length": 32.0, "yaw": -90.0, "tris": 14000, "split": ".",
        "exclude": r"missle|^Default_2|_dam_|Nippel",
        "rules": [
            {"name": r"^Tire_low|^Disc", "bone": "WHEEL#"},
            {"box": (-17.0, 3.5, -6.0, 6.0, 6.0, 14.0), "bone": "TURRET"},
        ],
        "muzzles": {"WEAPONA": ("TURRET", "rear")},
        "tint": ((180, 154, 110), None, 1.0),
        "rims": {"WHEEL": ("rubber", 0.6)},
        "engine": "front",
    },
    # M1097 Avenger by scout., CC-BY: Stinger pods either side of a turret drum on a HMMWV. The retail
    # Draw module turns TURRET01 and elevates TURRETEL01.
    "avenger": {
        "model": "AVGXAVNG", "stem": "gxavng3", "length": 23.0, "yaw": 90.0, "tris": 14000, "split": ".",
        "parents": {"TURRETEL01": "TURRET01"}, "pivots": {"TURRETEL01": "centre"},
        "muzzles": {"TURRETFX01": "TURRETEL01", "TURRETFX02": "TURRETEL01"},
        "rules": [
            {"name": r"Wheel_Clean", "bone": "WHEEL#"},
            {"box": (-10.5, -2.0, 3.0, 6.0, 9.6, 13.0), "bone": "TURRETEL01"},
            {"box": (-10.5, -2.0, -6.0, -3.0, 9.6, 13.0), "bone": "TURRETEL01"},
            {"box": (-11.0, -1.0, -3.2, 3.2, 6.4, 13.0), "bone": "TURRET01"},
        ],
        "tires": True,
        "finishes": [(r"Glass", "glass")],
        "tint": ((180, 154, 110), None, 1.0),
        "rims": {"TIRE": ("rubber", 0.62)},
        "engine": "front",
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
