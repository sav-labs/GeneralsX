# Skirmish map generator

`make_map.py` builds a Zero Hour skirmish map with the GeneralsX mechanics from a few parameters:

- Every base gets indestructible bunkers and artillery in front, supply docks with large reserves,
  and two unmanned, indestructible dozers of other generals. Capture a dozer to build for that
  general too.
- Between the bases there are fenced, capturable GLA compounds.
- Each base row has a capturable airfield, war factory or power plant, plus a hospital or repair
  bay and oil derricks.
- Capturable superweapons stand in the middle.

## Make a map

```bash
python3 scripts/tooling/maps/make_map.py --players 6 --biome snow --layout river --seed 42 \
    --name "Ice River" --out ~/maps --preview ~/maps/preview
```

| Option | Values | Default |
|---|---|---|
| `--players` | 2, 4, 6, 8 (split into west and east teams) | 4 |
| `--biome` | `temperate`, `desert`, `snow` | `temperate` |
| `--layout` | `lines` (open ground, superweapons on the centre line), `river` (a winding river between the teams, a bridge per base row, superweapons on each bank) | `lines` |
| `--seed` | any integer; the same parameters always give the same map | 1 |
| `--name` | display name; the map is saved as `GX <name>` | built from the parameters |
| `--out` | folder that receives `GX <name>/GX <name>.map` and `.tga` | current folder |
| `--repo` | repo root: writes into `content/Maps` (shipped in GeneralsXContent.big) and adds the name to `content/Data/generalsx.str` | |
| `--preview` | folder for a top view (PNG) and a perspective view (JPG) | |

To play a map without rebuilding the game, copy its `GX <name>` folder into the `Maps` folder in
the game's user data directory. The skirmish list then shows it under its file name. To ship a
map with the game, run the command with `--repo .` and commit the result.

Requirements: Python 3 with numpy and Pillow.

## Hand-made layouts

The maps shipped in `content/Maps` come from the layout modules (`twin_rivers.py`,
`mountain_pass.py`, `desert_oasis.py`, `frozen_divide.py`, `city_lines.py`, `forest_duel.py`).
`generate_maps.py <repo root>` regenerates them. `test_maps.py` checks that the committed files
match their generators. Shared pieces, such as the base kit, compounds and AI waypoints, live in
`kit.py`. The terrain and object writer is `mapgen.py` on top of `mapfile.py`.
