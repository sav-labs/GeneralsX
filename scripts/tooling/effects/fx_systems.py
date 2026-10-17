"""Particle systems and FX lists of the GeneralsX effects pack.

GeneralsX @feature Claude 16/10/2026 Each system is a dict of retail ParticleSystem INI fields plus
the GeneralsX FlipbookGrid / FlipbookRandom fields; write_ini() turns them into the INI the game
loads from Data\\INI\\GeneralsX.
FX lists replace retail FXList definitions by name; they keep the retail sounds, view shake and
terrain scorch and only swap the particles. Everything here is client-side presentation: FX
lists and particle systems never feed back into game logic, so replays and multiplayer sync are
unaffected. Debris objects (ObjectCreationList) are logic objects and are not touched.

Units follow the retail INI: distances in world units, times in logic frames (30 per second),
rates per frame. Colours are 0..255 keyed on particle age in frames.
"""

DEFAULTS = {
    "Priority": "DEATH_EXPLOSION",
    "IsOneShot": "No",
    "Shader": "ALPHA",
    "Type": "PARTICLE",
    "AngleZ": (0.0, 6.28),
    "AngularRateZ": (0.0, 0.0),
    "AngularDamping": (1.0, 1.0),
    "VelocityDamping": (1.0, 1.0),
    "Gravity": 0.0,
    "Lifetime": (30.0, 30.0),
    "SystemLifetime": 1,
    "Size": (10.0, 10.0),
    "StartSizeRate": (0.0, 0.0),
    "SizeRate": (0.0, 0.0),
    "SizeRateDamping": (1.0, 1.0),
    "Alpha": [(1.0, 1.0, 0)],
    "Color": [((255, 255, 255), 0)],
    "BurstDelay": (99999.0, 99999.0),
    "BurstCount": (1.0, 1.0),
    "InitialDelay": (0.0, 0.0),
    "DriftVelocity": (0.0, 0.0, 0.0),
    "VelocityType": "SPHERICAL",
    "VelSpherical": (0.0, 0.0),
    "VolumeType": "POINT",
    "IsHollow": "No",
    "IsGroundAligned": "No",
    "IsEmitAboveGroundOnly": "No",
    "IsParticleUpTowardsEmitter": "No",
    "FlipbookGrid": 0,
    "FlipbookRandom": "No",
}


def system(**fields):
    s = dict(DEFAULTS)
    s.update(fields)
    return s


SYSTEMS = {
    # ---- Tank death explosion (FX_GenericTankDeathExplosion) ----------------------------------
    # Bright flash that lights everything for a few frames.
    "GXTankBlastFlash": system(
        Shader="ADDITIVE", ParticleName="gxfx_flash.tga",
        Lifetime=(7, 7), Size=(40, 40), SizeRate=(3, 3), SizeRateDamping=(0.7, 0.7),
        Color=[((230, 170, 100), 0), ((180, 80, 20), 3), ((0, 0, 0), 7)],
        BurstCount=(1, 1), AngleZ=(0, 6.28)),
    # Orange light pool on the ground under the blast.
    "GXTankBlastGroundGlow": system(
        Shader="ADDITIVE", ParticleName="gxfx_spark.tga", IsGroundAligned="Yes",
        Lifetime=(26, 26), Size=(90, 90), SizeRate=(1.0, 1.0), SizeRateDamping=(0.9, 0.9),
        Color=[((230, 120, 40), 0), ((120, 40, 10), 12), ((0, 0, 0), 26)],
        BurstCount=(1, 1)),
    # Main fireball: a cluster of billowing flipbook puffs that rise and cool into smoke.
    "GXTankBlastFireball": system(
        # The baked flipbook holds the whole blast (flash, fireball, burning-out, rolling smoke) over
        # 72 frames, so a few large overlapping copies play it once each.
        ParticleName="gxfx_fireball.tga", FlipbookGrid=8, AngleZ=(-0.12, 0.12),
        Lifetime=(66, 78), Size=(52, 64), SizeRate=(0.25, 0.35), SizeRateDamping=(0.98, 0.98),
        Alpha=[(1.0, 1.0, 0), (1.0, 1.0, 56), (0.0, 0.0, 78)],
        Color=[((255, 255, 255), 0)],
        BurstCount=(3, 3), VelocityDamping=(0.85, 0.88), DriftVelocity=(0.0, 0.0, 0.12),
        VelocityType="SPHERICAL", VelSpherical=(0.2, 0.5),
        VolumeType="SPHERE", VolSphereRadius=4.0),
    # Smaller secondary blasts a moment later, as fuel and ammunition go off.
    "GXTankBlastSecondary": system(
        ParticleName="gxfx_fireball.tga", FlipbookGrid=8, AngleZ=(-0.12, 0.12),
        Lifetime=(48, 58), Size=(24, 30), SizeRate=(0.15, 0.25), SizeRateDamping=(0.98, 0.98),
        Alpha=[(1.0, 1.0, 0), (1.0, 1.0, 40), (0.0, 0.0, 58)],
        BurstDelay=(3, 6), BurstCount=(1, 1), SystemLifetime=18, InitialDelay=(5, 5),
        Gravity=0.02, VelocityDamping=(0.85, 0.85),
        VelocityType="SPHERICAL", VelSpherical=(0.6, 1.2),
        VolumeType="SPHERE", VolSphereRadius=12.0),
    # Dust ring racing out along the ground, fast at first and slowing as it thins.
    "GXTankBlastShockwave": system(
        ParticleName="gxfx_ring.tga", IsGroundAligned="Yes", AngleZ=(0, 6.28),
        Lifetime=(18, 18), Size=(8, 8), SizeRate=(9, 9), SizeRateDamping=(0.82, 0.82),
        Alpha=[(0.55, 0.55, 0), (0.35, 0.35, 7), (0.0, 0.0, 18)],
        Color=[((215, 196, 160), 0)],
        BurstCount=(1, 1)),
    # Brown dust thrown up and outwards around the hull.
    "GXTankBlastDust": system(
        ParticleName="gxfx_dust.tga", FlipbookGrid=8, AngleZ=(-0.15, 0.15),
        Lifetime=(60, 85), Size=(14, 20), SizeRate=(0.5, 0.7), SizeRateDamping=(0.965, 0.97),
        Alpha=[(0.0, 0.0, 0), (0.9, 0.9, 5), (0.0, 0.0, 85)],
        Color=[((235, 225, 210), 0)],
        BurstCount=(14, 14), VelocityDamping=(0.9, 0.92), Gravity=0.004,
        VelocityType="OUTWARD", VelOutward=(1.6, 2.8), VelOutwardOther=(0.1, 0.5),
        VolumeType="CYLINDER", VolCylinderRadius=8.0, VolCylinderLength=1.0, IsHollow="Yes"),
    # Fast glowing embers.
    "GXTankBlastEmbers": system(
        Shader="ADDITIVE", ParticleName="gxfx_spark.tga",
        Lifetime=(18, 40), Size=(1.0, 2.0), SizeRate=(-0.02, -0.02),
        Color=[((255, 230, 170), 0), ((255, 110, 30), 16), ((0, 0, 0), 40)],
        BurstCount=(40, 40), Gravity=-0.12, VelocityDamping=(0.95, 0.97),
        VelocityType="OUTWARD", VelOutward=(1.5, 5.0), VelOutwardOther=(1.5, 5.5),
        VolumeType="CYLINDER", VolCylinderRadius=4.0, VolCylinderLength=4.0),
    # Hot metal sparks streaking outwards and arcing down.
    "GXTankBlastSparks": system(
        Shader="ADDITIVE", ParticleName="gxfx_streak.tga", IsParticleUpTowardsEmitter="Yes",
        Lifetime=(12, 26), Size=(3.0, 5.0), SizeRate=(-0.1, -0.1),
        Color=[((255, 240, 200), 0), ((255, 140, 40), 10), ((0, 0, 0), 26)],
        BurstCount=(36, 36), Gravity=-0.18, VelocityDamping=(0.93, 0.95),
        VelocityType="OUTWARD", VelOutward=(3.0, 7.0), VelOutwardOther=(1.5, 5.0),
        VolumeType="CYLINDER", VolCylinderRadius=2.0, VolCylinderLength=3.0),
    # A whole baked spark shower over the hull, for the dense glow the single streaks lack.
    "GXTankBlastSparkBurst": system(
        Shader="ADDITIVE", ParticleName="gxfx_sparks.tga", FlipbookGrid=8, AngleZ=(-0.4, 0.4),
        Lifetime=(30, 30), Size=(34, 40), Color=[((255, 255, 255), 0)],
        BurstCount=(2, 2), VolumeType="SPHERE", VolSphereRadius=3.0),
    # Thick black smoke that rolls up from the fireball.
    "GXTankBlastSmoke": system(
        ParticleName="gxfx_smoke.tga", FlipbookGrid=8, AngleZ=(-0.12, 0.12),
        Lifetime=(120, 160), Size=(20, 26), SizeRate=(0.3, 0.4), SizeRateDamping=(0.99, 0.99),
        Alpha=[(0.0, 0.0, 0), (0.9, 0.9, 14), (0.6, 0.6, 80), (0.0, 0.0, 160)],
        Color=[((150, 144, 138), 0), ((200, 196, 190), 110)],
        BurstDelay=(2, 2), BurstCount=(2, 2), SystemLifetime=10, InitialDelay=(6, 6),
        DriftVelocity=(0.12, 0.05, 0.42), VelocityDamping=(0.92, 0.94),
        VelocityType="SPHERICAL", VelSpherical=(0.4, 0.9),
        VolumeType="SPHERE", VolSphereRadius=8.0),

    # ---- Burning wreck (about 6 s, until the retail hulk has sunk into the ground) -------------
    "GXWreckFire": system(
        # Baked fire carries its own colour and soot; alpha blended so the soot darkens.
        Priority="WEAPON_EXPLOSION", ParticleName="gxfx_flame.tga", FlipbookGrid=8,
        Lifetime=(28, 36), Size=(10, 14), SizeRate=(0.05, 0.1), SizeRateDamping=(0.97, 0.97),
        AngleZ=(-0.1, 0.1),
        Alpha=[(0.0, 0.0, 0), (1.0, 1.0, 4), (1.0, 1.0, 24), (0.0, 0.0, 36)],
        Color=[((255, 255, 255), 0)],
        BurstDelay=(2, 3), BurstCount=(1, 1), SystemLifetime=170,
        DriftVelocity=(0.0, 0.0, 0.3),
        VolumeType="CYLINDER", VolCylinderRadius=6.0, VolCylinderLength=3.0),
    "GXWreckSmoke": system(
        Priority="WEAPON_EXPLOSION", ParticleName="gxfx_smoke.tga", FlipbookGrid=8, AngleZ=(-0.12, 0.12),
        Lifetime=(140, 180), Size=(10, 14), SizeRate=(0.12, 0.16), SizeRateDamping=(0.995, 0.995),
        Alpha=[(0.0, 0.0, 0), (0.85, 0.85, 18), (0.5, 0.5, 100), (0.0, 0.0, 180)],
        Color=[((120, 114, 108), 0), ((190, 186, 180), 130)],
        BurstDelay=(5, 8), BurstCount=(1, 1), SystemLifetime=200, InitialDelay=(20, 20),
        DriftVelocity=(0.14, 0.06, 0.5),
        VolumeType="CYLINDER", VolCylinderRadius=4.0, VolCylinderLength=2.0),
    "GXWreckEmbers": system(
        Priority="WEAPON_EXPLOSION", Shader="ADDITIVE", ParticleName="gxfx_spark.tga",
        Lifetime=(30, 50), Size=(0.7, 1.4),
        Color=[((255, 200, 120), 0), ((255, 90, 20), 24), ((0, 0, 0), 50)],
        BurstDelay=(4, 10), BurstCount=(1, 2), SystemLifetime=170,
        DriftVelocity=(0.08, 0.03, 0.0), Gravity=0.01, VelocityDamping=(0.97, 0.97),
        VelocityType="OUTWARD", VelOutward=(0.1, 0.4), VelOutwardOther=(0.6, 1.2),
        VolumeType="CYLINDER", VolCylinderRadius=6.0, VolCylinderLength=2.0),
    "GXWreckHeatGlow": system(
        Priority="WEAPON_EXPLOSION", Shader="ADDITIVE", ParticleName="gxfx_spark.tga", IsGroundAligned="Yes",
        Lifetime=(40, 40), Size=(34, 40),
        Color=[((0, 0, 0), 0), ((110, 50, 14), 10), ((110, 50, 14), 30), ((0, 0, 0), 40)],
        BurstDelay=(30, 30), BurstCount=(1, 1), SystemLifetime=160),

    # ---- Damage states: retail systems redefined in place --------------------------------------
    # These names are attached to bones of damaged and badly damaged buildings and vehicles by the
    # retail art INI (W3DModelDraw ParticleSysBone, TransitionDamageFX), thousands of places in all.
    # Redefining them keeps the retail placement and only changes the look. The scale and emission
    # rates stay close to retail so the particle budget does not grow.
    "SmolderingSmoke": system(
        Priority="WEAPON_EXPLOSION", ParticleName="gxfx_smoke.tga", FlipbookGrid=8,
        AngleZ=(-0.12, 0.12),
        Lifetime=(90, 120), Size=(5.0, 6.5), SizeRate=(0.25, 0.35), SizeRateDamping=(0.985, 0.99),
        Alpha=[(0.0, 0.0, 0), (0.85, 0.85, 8), (0.45, 0.45, 70), (0.0, 0.0, 120)],
        Color=[((140, 134, 128), 0), ((210, 206, 200), 100)],
        BurstDelay=(5, 9), BurstCount=(1, 1), SystemLifetime=0,
        DriftVelocity=(-0.05, 0.08, 0.24), VelocityDamping=(0.9, 0.92),
        VelocityType="OUTWARD", VelOutward=(0.1, 0.1), VelOutwardOther=(0.0, 0.0),
        VolumeType="SPHERE", VolSphereRadius=0.5),
    "SmolderingFire": system(
        Priority="SEMI_CONSTANT", ParticleName="gxfx_flame.tga", FlipbookGrid=8,
        AngleZ=(-0.1, 0.1),
        Lifetime=(22, 28), Size=(7.0, 9.0), SizeRate=(0.05, 0.1), SizeRateDamping=(0.95, 0.95),
        Alpha=[(0.0, 0.0, 0), (1.0, 1.0, 3), (1.0, 1.0, 18), (0.0, 0.0, 28)],
        Color=[((255, 255, 255), 0)],
        BurstDelay=(1, 3), BurstCount=(1, 1), SystemLifetime=0,
        DriftVelocity=(-0.05, 0.08, 0.2),
        VolumeType="CYLINDER", VolCylinderRadius=2.0, VolCylinderLength=1.0),
    "SmolderingFlameCore": system(
        Priority="WEAPON_EXPLOSION", Shader="ADDITIVE", ParticleName="gxfx_spark.tga",
        Lifetime=(6, 8), Size=(3.0, 4.5), SizeRate=(0.3, 0.3), SizeRateDamping=(0.5, 0.5),
        Color=[((255, 236, 190), 0), ((255, 150, 60), 4), ((0, 0, 0), 8)],
        BurstDelay=(0, 1), BurstCount=(1, 1), SystemLifetime=0, InitialDelay=(2, 3),
        DriftVelocity=(-0.1, 0.1, 0.2), VelocityDamping=(0.8, 0.95), Gravity=0.05,
        VolumeType="SPHERE", VolSphereRadius=0.4),
    # Badly damaged vehicles.
    "SmallLightSmokeColumn": system(
        Priority="SEMI_CONSTANT", ParticleName="gxfx_smoke.tga", FlipbookGrid=8, AngleZ=(-0.12, 0.12),
        Lifetime=(60, 80), Size=(3.5, 5.0), SizeRate=(0.25, 0.4), SizeRateDamping=(0.97, 0.975),
        Alpha=[(0.0, 0.0, 0), (0.75, 0.75, 5), (0.0, 0.0, 80)],
        Color=[((150, 146, 140), 0), ((215, 211, 205), 60)],
        BurstDelay=(2, 2), BurstCount=(1, 1), SystemLifetime=0,
        DriftVelocity=(0.1, 0.15, 0.18),
        VolumeType="CYLINDER", VolCylinderRadius=1.0, VolCylinderLength=0.1),
}


def _structure_blast(count, size, speed, radius):
    return system(
        ParticleName="gxfx_fireball.tga", FlipbookGrid=8, AngleZ=(-0.12, 0.12),
        Lifetime=(60, 72), Size=size, SizeRate=(0.3, 0.45), SizeRateDamping=(0.97, 0.98),
        Alpha=[(1.0, 1.0, 0), (1.0, 1.0, 50), (0.0, 0.0, 72)],
        BurstDelay=(99999, 99999), BurstCount=count, Gravity=0.02, VelocityDamping=(0.86, 0.9),
        DriftVelocity=(0.0, 0.0, 0.25),
        VelocityType="OUTWARD", VelOutward=speed, VelOutwardOther=(0.3, 0.9),
        VolumeType="CYLINDER", VolCylinderRadius=radius, VolCylinderLength=0.0)


def _structure_dust(count, size, rate, speed, radius, length, gravity):
    return system(
        ParticleName="gxfx_dust.tga", FlipbookGrid=8, AngleZ=(-0.15, 0.15),
        Lifetime=(150, 200), Size=size, SizeRate=rate, SizeRateDamping=(0.95, 0.96),
        Alpha=[(0.0, 0.0, 0), (0.7, 0.7, 8), (0.35, 0.35, 90), (0.0, 0.0, 200)],
        Color=[((190, 180, 166), 0), ((176, 168, 156), 60)],
        BurstDelay=(99999, 99999), BurstCount=count, SystemLifetime=20,
        Gravity=gravity * 0.1, VelocityDamping=(0.88, 0.9),
        VelocityType="OUTWARD", VelOutward=speed, VelOutwardOther=(0.0, 0.3),
        VolumeType="CYLINDER", VolCylinderRadius=radius, VolCylinderLength=length)


# Damage transitions of structures: a burst of fire and a cloud of dust and debris when a building
# drops to damaged or badly damaged. Same names, counts and extents as retail.
SYSTEMS.update({
    "StructureTransitionTinyExplosion": _structure_blast((2, 3), (14, 20), (0.8, 1.2), 2.0),
    "StructureTransitionSmallExplosion": _structure_blast((4, 5), (22, 30), (1.6, 2.4), 5.0),
    "StructureTransitionMediumExplosion": _structure_blast((6, 8), (24, 32), (3.0, 4.5), 15.0),
    "StructureTransitionLargeExplosion": _structure_blast((8, 10), (26, 36), (4.0, 6.0), 30.0),
    "StructureTransitionTinySmoke": _structure_dust((5, 5), (8, 12), (0.3, 0.45), (1.0, 2.0), 1.0, 0.0, 0.1),
    "StructureTransitionSmallSmoke": _structure_dust((15, 15), (14, 20), (0.4, 0.6), (3.0, 4.5), 10.0, 0.0, 0.25),
    "StructureTransitionMediumSmoke": _structure_dust((15, 15), (16, 22), (0.5, 0.8), (3.0, 4.5), 30.0, 0.0, 0.0),
    "StructureTransitionLargeSmoke": _structure_dust((24, 24), (18, 24), (0.6, 0.9), (3.0, 4.5), 50.0, 25.0, 0.2),
})

# Gun fire and shell impacts: retail systems behind WeaponFX_GenericTankGunNoTracer (most tank guns)
# and WeaponFX_GenericTankShellDetonation / WeaponFX_RocketBuggyMissileDetonation (shell and rocket
# hits), redefined in place so every weapon that uses them changes. The FX lists orient the muzzle
# systems to the turret, so ORTHO X points down the barrel.
SYSTEMS.update({
    # Fireball pushed out of the muzzle.
    "TankMuzzleFlashFlame": system(
        Priority="WEAPON_EXPLOSION", ParticleName="gxfx_burst.tga", FlipbookGrid=8, AngleZ=(-0.3, 0.3),
        Lifetime=(10, 14), Size=(4.0, 6.0), SizeRate=(0.5, 0.7), SizeRateDamping=(0.9, 0.9),
        Alpha=[(1.0, 1.0, 0), (1.0, 1.0, 8), (0.0, 0.0, 14)],
        BurstCount=(3, 3), SystemLifetime=10, VelocityDamping=(0.6, 0.75),
        VelocityType="ORTHO", VelOrthoX=(1.5, 4.5), VelOrthoY=(-0.3, 0.3), VelOrthoZ=(-0.2, 0.3),
        VolumeType="CYLINDER", VolCylinderRadius=0.5, VolCylinderLength=0.0),
    # Grey gun smoke that drifts off the barrel.
    "TankMuzzleFlashSmoke": system(
        Priority="WEAPON_EXPLOSION", ParticleName="gxfx_smoke.tga", FlipbookGrid=8, AngleZ=(-0.12, 0.12),
        Lifetime=(60, 80), Size=(4.0, 6.0), SizeRate=(0.35, 0.5), SizeRateDamping=(0.97, 0.98),
        Alpha=[(0.0, 0.0, 0), (0.7, 0.7, 4), (0.35, 0.35, 40), (0.0, 0.0, 80)],
        Color=[((210, 206, 200), 0), ((235, 232, 228), 60)],
        BurstCount=(4, 4), SystemLifetime=10, VelocityDamping=(0.82, 0.88),
        DriftVelocity=(-0.05, 0.05, 0.12),
        VelocityType="ORTHO", VelOrthoX=(0.5, 2.5), VelOrthoY=(-0.8, 0.8), VelOrthoZ=(0.1, 0.6),
        VolumeType="CYLINDER", VolCylinderRadius=0.8, VolCylinderLength=0.0),
    # Short white flash at the muzzle instead of the retail lens flare.
    "TankMuzzleFlare": system(
        Priority="CRITICAL", Shader="ADDITIVE", ParticleName="gxfx_flash.tga",
        Lifetime=(5, 5), Size=(12, 12), SizeRate=(2.0, 2.0), SizeRateDamping=(0.6, 0.6),
        Color=[((255, 246, 220), 0), ((255, 160, 70), 2), ((0, 0, 0), 5)],
        BurstCount=(1, 1), SystemLifetime=1),
    # Dust kicked up from the ground by the muzzle blast.
    "TankMuzzleWave": system(
        Priority="WEAPON_EXPLOSION", ParticleName="gxfx_dust.tga", FlipbookGrid=8, AngleZ=(-0.15, 0.15),
        Lifetime=(45, 60), Size=(5.0, 8.0), SizeRate=(0.3, 0.45), SizeRateDamping=(0.96, 0.97),
        Alpha=[(0.0, 0.0, 0), (0.75, 0.75, 4), (0.0, 0.0, 60)],
        Color=[((235, 225, 210), 0)],
        BurstCount=(4, 4), SystemLifetime=1, VelocityDamping=(0.85, 0.9),
        VelocityType="ORTHO", VelOrthoX=(0.5, 2.0), VelOrthoY=(-1.5, 1.5), VelOrthoZ=(0.0, 0.3),
        VolumeType="CYLINDER", VolCylinderRadius=2.0, VolCylinderLength=0.0),
    # Shell and rocket hit: a quick fireball. UseCallersRadius in the FX list scales the volume to
    # the weapon's damage radius.
    "BuggyMissileExplosion": system(
        Priority="WEAPON_EXPLOSION", ParticleName="gxfx_burst.tga", FlipbookGrid=8, AngleZ=(-0.15, 0.15),
        Lifetime=(18, 24), Size=(8.0, 12.0), SizeRate=(0.35, 0.5), SizeRateDamping=(0.93, 0.95),
        Alpha=[(1.0, 1.0, 0), (1.0, 1.0, 14), (0.0, 0.0, 24)],
        BurstCount=(3, 3), SystemLifetime=10, VelocityDamping=(0.75, 0.8),
        VelocityType="SPHERICAL", VelSpherical=(0.3, 0.8),
        VolumeType="SPHERE", VolSphereRadius=0.0),
    "BuggyMissileExplosionSmoke": system(
        Priority="WEAPON_EXPLOSION", ParticleName="gxfx_smoke.tga", FlipbookGrid=8, AngleZ=(-0.12, 0.12),
        Lifetime=(90, 120), Size=(8.0, 12.0), SizeRate=(0.2, 0.3), SizeRateDamping=(0.99, 0.99),
        Alpha=[(0.0, 0.0, 0), (0.8, 0.8, 6), (0.4, 0.4, 60), (0.0, 0.0, 120)],
        Color=[((150, 144, 138), 0), ((205, 200, 194), 90)],
        BurstCount=(3, 3), SystemLifetime=10, VelocityDamping=(0.8, 0.85),
        DriftVelocity=(0.05, 0.03, 0.2),
        VelocityType="SPHERICAL", VelSpherical=(0.3, 0.6),
        VolumeType="SPHERE", VolSphereRadius=1.0),
    # Badly damaged vehicles: several of these hang on the Smoke bones of most tanks.
    "SmokeSmallContinuous01": system(
        Priority="CONSTANT", ParticleName="gxfx_smoke.tga", FlipbookGrid=8, AngleZ=(-0.12, 0.12),
        Lifetime=(50, 60), Size=(2.0, 3.0), SizeRate=(0.25, 0.4), SizeRateDamping=(0.97, 0.98),
        Alpha=[(0.0, 0.0, 0), (0.7, 0.7, 4), (0.0, 0.0, 60)],
        Color=[((120, 114, 108), 0), ((200, 196, 190), 45)],
        BurstDelay=(1, 1), BurstCount=(1, 1), SystemLifetime=0, Gravity=0.05,
        VelocityDamping=(0.98, 0.98), DriftVelocity=(0.08, 0.16, 0.01),
        VelocityType="OUTWARD", VelOutward=(0.08, 0.1), VelOutwardOther=(0.0, 0.0),
        VolumeType="SPHERE", VolSphereRadius=4.0),
    # A vehicle dropping to badly damaged (FX_BattleMasterDamageTransition, most vehicles).
    "BattleMasterTransitionExplosion": system(
        Priority="UNIT_DAMAGE_FX", ParticleName="gxfx_burst.tga", FlipbookGrid=8, AngleZ=(-0.15, 0.15),
        Lifetime=(18, 24), Size=(8.0, 11.0), SizeRate=(0.3, 0.45), SizeRateDamping=(0.93, 0.95),
        Alpha=[(1.0, 1.0, 0), (1.0, 1.0, 14), (0.0, 0.0, 24)],
        BurstCount=(3, 3), SystemLifetime=10, VelocityDamping=(0.75, 0.8),
        VelocityType="SPHERICAL", VelSpherical=(0.3, 0.7),
        VolumeType="SPHERE", VolSphereRadius=3.0),
})

def _gun_flash(size, lifetime=3):
    # One random flash per shot from the gxfx_muzzle frames; ADDITIVE, so it only brightens.
    return system(
        Priority="WEAPON_EXPLOSION", Shader="ADDITIVE", ParticleName="gxfx_muzzle.tga",
        FlipbookGrid=4, FlipbookRandom="Yes",
        Lifetime=(lifetime, lifetime), Size=size, SizeRate=(0.4, 0.4), SizeRateDamping=(0.7, 0.7),
        Color=[((255, 255, 255), 0), ((150, 110, 70), lifetime - 1), ((0, 0, 0), lifetime)],
        BurstCount=(1, 1), SystemLifetime=1, VelocityType="ORTHO", VelOrthoX=(0.0, 0.0),
        VelOrthoY=(0.0, 0.0), VelOrthoZ=(0.0, 0.0))


def _struck_sparks(size):
    # A whole spark shower in one sprite (gxfx_sparks): flash, sparks arcing out, cooling, falling.
    return system(
        Priority="UNIT_DAMAGE_FX", Shader="ADDITIVE", ParticleName="gxfx_sparks.tga", FlipbookGrid=8,
        AngleZ=(-0.3, 0.3), Lifetime=(18, 24), Size=size,
        Color=[((255, 255, 255), 0), ((255, 255, 255), 14), ((0, 0, 0), 24)],
        BurstCount=(1, 1), SystemLifetime=1)


def _struck_smoke(count, size, lifetime, alpha):
    return system(
        Priority="UNIT_DAMAGE_FX", ParticleName="gxfx_smoke.tga", FlipbookGrid=8, AngleZ=(-0.12, 0.12),
        Lifetime=lifetime, Size=size, SizeRate=(0.25, 0.35), SizeRateDamping=(0.96, 0.97),
        Alpha=[(0.0, 0.0, 0), (alpha, alpha, 3), (alpha * 0.5, alpha * 0.5, lifetime[0] // 2),
               (0.0, 0.0, lifetime[1])],
        Color=[((170, 164, 156), 0), ((215, 211, 205), lifetime[0] // 2)],
        BurstCount=count, SystemLifetime=1, VelocityDamping=(0.8, 0.85),
        DriftVelocity=(0.08, 0.16, 0.08),
        VelocityType="ORTHO", VelOrthoX=(0.3, 1.5), VelOrthoY=(-0.8, 0.8), VelOrthoZ=(0.0, 0.4))


# Machine gun fire and hits on armour: WeaponFX_GenericMachineGunFire and its relatives flash
# GattlingCannonLenzflare at the muzzle; FX_DamageTankStruck and FX_DamageTankStruckSmallArms (every
# vehicle hit) throw TankStruckSparks, a flare and smoke. Small tank guns use TankSmallMuzzle*.
SYSTEMS.update({
    "GattlingCannonLenzflare": _gun_flash((5.0, 7.0)),
    "GattlingCannonLenzflareIntense": _gun_flash((8.0, 10.0)),
    "TankStruckSparks": _struck_sparks((12.0, 16.0)),
    "SmallTankStruckSparks": _struck_sparks((8.0, 11.0)),
    "TankStruckLenzflare": _gun_flash((10.0, 12.0), lifetime=4),
    "TankStruckSmoke": _struck_smoke((3, 3), (3.0, 4.5), (70, 90), 0.6),
    "TankStruckSmallArmsSmoke": _struck_smoke((1, 1), (1.5, 2.5), (25, 35), 0.45),
    "TankSmallMuzzleFlare": _gun_flash((7.0, 9.0), lifetime=4),
    "TankSmallMuzzleFlashFlame": system(**{**SYSTEMS["TankMuzzleFlashFlame"],
                                           "Size": (2.5, 3.5), "VelOrthoX": (1.0, 3.0)}),
    "TankSmallMuzzleFlashSmoke": system(**{**SYSTEMS["TankMuzzleFlashSmoke"],
                                           "Size": (2.5, 4.0), "BurstCount": (3, 3)}),
})

def _wire_sparks(size, delay):
    # Shorted wiring on damaged buildings: a spark shower every few seconds instead of loose dots.
    return system(
        Priority="CONSTANT", Shader="ADDITIVE", ParticleName="gxfx_sparks.tga", FlipbookGrid=8,
        AngleZ=(-0.4, 0.4), Lifetime=(16, 22), Size=size,
        Color=[((255, 255, 255), 0), ((255, 255, 255), 12), ((0, 0, 0), 22)],
        BurstDelay=delay, BurstCount=(1, 1), SystemLifetime=0,
        VolumeType="SPHERE", VolSphereRadius=0.5)


# Damaged buildings, after SmolderingSmoke and SmolderingFire the most used bone systems: steam from
# broken pipes and sparks from torn wiring.
SYSTEMS.update({
    "SteamVent": system(
        Priority="CONSTANT", ParticleName="gxfx_smoke.tga", FlipbookGrid=8, AngleZ=(-0.12, 0.12),
        Lifetime=(55, 70), Size=(5.0, 7.0), SizeRate=(0.3, 0.45), SizeRateDamping=(0.96, 0.97),
        Alpha=[(0.0, 0.0, 0), (0.55, 0.55, 5), (0.25, 0.25, 35), (0.0, 0.0, 70)],
        Color=[((235, 235, 235), 0), ((250, 250, 250), 40)],
        BurstDelay=(3, 10), BurstCount=(1, 1), SystemLifetime=0, Gravity=0.0,
        VelocityDamping=(0.9, 0.92), DriftVelocity=(0.1, 0.15, 0.35),
        VelocityType="OUTWARD", VelOutward=(0.3, 1.2), VelOutwardOther=(0.5, 1.0),
        VolumeType="SPHERE", VolSphereRadius=0.25),
    "SparksMedium": _wire_sparks((6.0, 9.0), (15, 60)),
    "LiveWireSparks": _wire_sparks((4.0, 6.0), (20, 90)),
    "LiveWireSparks02": _wire_sparks((4.0, 6.0), (20, 90)),
})

# Particle systems of one FX list entry: (system, offset x y z).
FXLISTS = {
    "FX_GenericTankDeathExplosion": {
        "particles": [
            ("GXTankBlastFlash", (0, 0, 10)),
            ("GXTankBlastGroundGlow", (0, 0, 1)),
            ("GXTankBlastFireball", (0, 0, 8)),
            ("GXTankBlastSecondary", (0, 0, 8)),
            ("GXTankBlastShockwave", (0, 0, 1)),
            ("GXTankBlastDust", (0, 0, 2)),
            ("GXTankBlastEmbers", (0, 0, 6)),
            ("GXTankBlastSparks", (0, 0, 5)),
            ("GXTankBlastSparkBurst", (0, 0, 6)),
            ("GXTankBlastSmoke", (0, 0, 12)),
            ("GXWreckFire", (0, 0, 6)),
            ("GXWreckSmoke", (0, 0, 12)),
            ("GXWreckEmbers", (0, 0, 6)),
            ("GXWreckHeatGlow", (0, 0, 1)),
        ],
        # Retail nuggets kept as they are.
        "extra": """  LightPulse
    Color = R:255 G:150 B:70
    Radius = 90
    IncreaseTime = 0
    DecreaseTime = 900
  End
  ViewShake
    Type = STRONG
  End
  TerrainScorch
    Type = RANDOM
    Radius = 15
  End
  Sound
    Name = TankDie
  End
""",
    },
}


def _pair(v):
    return "%.2f %.2f" % (float(v[0]), float(v[1]))


def write_system(name, s):
    out = ["ParticleSystem %s" % name]
    for key in ("Priority", "IsOneShot", "Shader", "Type", "ParticleName"):
        out.append("  %s = %s" % (key, s[key]))
    for key in ("AngleZ", "AngularRateZ", "AngularDamping", "VelocityDamping"):
        out.append("  %s = %s" % (key, _pair(s[key])))
    out.append("  Gravity = %.3f" % s["Gravity"])
    out.append("  Lifetime = %s" % _pair(s["Lifetime"]))
    out.append("  SystemLifetime = %d" % s["SystemLifetime"])
    for key in ("Size", "StartSizeRate", "SizeRate", "SizeRateDamping"):
        out.append("  %s = %s" % (key, _pair(s[key])))
    alpha = list(s["Alpha"]) + [(0.0, 0.0, 0)] * (8 - len(s["Alpha"]))
    for i, (lo, hi, frame) in enumerate(alpha):
        out.append("  Alpha%d = %.2f %.2f %d" % (i + 1, lo, hi, frame))
    color = list(s["Color"]) + [((0, 0, 0), 0)] * (8 - len(s["Color"]))
    for i, ((r, g, b), frame) in enumerate(color):
        out.append("  Color%d = R:%d G:%d B:%d %d" % (i + 1, r, g, b, frame))
    out.append("  ColorScale = 0.00 0.00")
    for key in ("BurstDelay", "BurstCount", "InitialDelay"):
        out.append("  %s = %s" % (key, _pair(s[key])))
    d = s["DriftVelocity"]
    out.append("  DriftVelocity = X:%.2f Y:%.2f Z:%.2f" % d)
    out.append("  VelocityType = %s" % s["VelocityType"])
    vt = s["VelocityType"]
    if vt == "SPHERICAL":
        out.append("  VelSpherical = %s" % _pair(s["VelSpherical"]))
    elif vt == "HEMISPHERICAL":
        out.append("  VelHemispherical = %s" % _pair(s["VelHemispherical"]))
    elif vt == "OUTWARD":
        out.append("  VelOutward = %s" % _pair(s["VelOutward"]))
        out.append("  VelOutwardOther = %s" % _pair(s["VelOutwardOther"]))
    elif vt == "ORTHO":
        # With OrientToObject in the FX list, X runs along the gun barrel.
        for axis in ("X", "Y", "Z"):
            out.append("  VelOrtho%s = %s" % (axis, _pair(s["VelOrtho" + axis])))
    out.append("  VolumeType = %s" % s["VolumeType"])
    if s["VolumeType"] == "SPHERE":
        out.append("  VolSphereRadius = %.2f" % s["VolSphereRadius"])
    elif s["VolumeType"] == "CYLINDER":
        out.append("  VolCylinderRadius = %.2f" % s["VolCylinderRadius"])
        out.append("  VolCylinderLength = %.2f" % s["VolCylinderLength"])
    for key in ("IsHollow", "IsGroundAligned", "IsEmitAboveGroundOnly", "IsParticleUpTowardsEmitter"):
        out.append("  %s = %s" % (key, s[key]))
    out.append("  WindMotion = Unused")
    if s["FlipbookGrid"]:
        out.append("  FlipbookGrid = %d" % s["FlipbookGrid"])
        out.append("  FlipbookRandom = %s" % s["FlipbookRandom"])
    out.append("End")
    return "\n".join(out) + "\n"


def write_fxlist(name, fx):
    out = ["FXList %s" % name]
    for sys_name, (x, y, z) in fx["particles"]:
        out += ["  ParticleSystem", "    Name = %s" % sys_name,
                "    Offset = X:%.1f Y:%.1f Z:%.1f" % (x, y, z), "  End"]
    return "\n".join(out) + "\n" + fx["extra"] + "End\n"


def write_ini():
    """Returns {archive path: INI text}. Particle systems come first so the FX lists find them."""
    header = "; GeneralsX effects pack: generated by scripts/tooling/effects/build_effects.py, do not edit.\n\n"
    systems = header + "\n".join(write_system(n, s) for n, s in SYSTEMS.items())
    fx = header + "\n".join(write_fxlist(n, f) for n, f in FXLISTS.items())
    return {
        "Data\\INI\\GeneralsX\\EffectsParticles.ini": systems,
        "Data\\INI\\GeneralsX\\EffectsFXList.ini": fx,
    }

# Most China vehicles (Battlemaster, Gattling tank) and the Humvee die through these retail lists,
# which have the same nuggets as FX_GenericTankDeathExplosion apart from the light, so they get the
# same explosion and burning wreck.
FXLISTS["FX_BattleMasterExplosionOneFinal"] = FXLISTS["FX_GenericTankDeathExplosion"]
FXLISTS["FX_GattlingExplosionOneFinal"] = FXLISTS["FX_GenericTankDeathExplosion"]
