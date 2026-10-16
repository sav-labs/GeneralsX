# Cameo renderer

Renders command bar buttons (120x96) and portraits (216x178, `Name_L`) for the new USA vehicles from the content thread's `.glb` sources, in the retail Zero Hour cameo look: low front quarter view, blue sky with clouds, sandy ground, dark navy bevel.

```bash
pip install bpy==5.2.2 pillow
python render_cameos.py <glb_dir> <out_dir> [--units crusader paladin ...] [--samples 48]
```

- `<glb_dir>` holds the model-sources release glbs (`crusader.glb`, `paladin.glb`, ...).
- Each unit writes `<Cameo>.png`, `<Cameo>_L.png` and 4x masters (`*_4x.png`).
- Paint follows the content tint (desert tan, amount 0.85); glass, tyres and lights keep their colour.
- Duplicate coplanar meshes in the glbs are dropped before rendering (they z-fight into black patches).

No retail art is read or written; the output comes from the CC0/CC-BY models listed in the content CREDITS.
