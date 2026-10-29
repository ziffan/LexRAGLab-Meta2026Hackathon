# Header B: Glimmer (local, effort low) (akta)

- key: `27e9393dbecb5d27a17d7e4a4c7280baf6bfd16ce2e9b6eaf1b8fd16de698c70`; main off series: `runs/grid/86e701f56a3bc5f83268b4cf8590d9dfe641773b8234b3e826c4c4db2b517c2e.json` (key `86e701f56a3bc5f83268b4cf8590d9dfe641773b8234b3e826c4c4db2b517c2e`)
- provider `lmstudio_local`, model `meta/muse-glimmer`, quantization `Q4_K_M`, effort `low`
- sources run: pasal, structure_schema; sources not run: fixed_size; **partial coverage**
- Not a reported number: comparison only (H-028); the main grid, frontier and selected profile stay Contributor.

## Points (header-on twins)

| Series | Setting | Chunker | Mode | Budget | Split | Span recall | Mean retrieved tokens | Dominated |
|---|---|---|---|---|---|---|---|---|
| Header B: Glimmer (local, effort low) (partial coverage) | `10fab4d684ca` | structure_handwritten | bm25 | 1000 | None | 0/1 = 0.000000 | 0/1 = 0.000000 | False |
| Header B: Glimmer (local, effort low) (partial coverage) | `3fa7201e820a` | structure_handwritten | dense | 1000 | None | 0/1 = 0.000000 | 0/1 = 0.000000 | False |
| Header B: Glimmer (local, effort low) (partial coverage) | `82ed8c5a7f98` | structure_handwritten | hybrid | 1000 | None | 0/1 = 0.000000 | 0/1 = 0.000000 | False |
| Header B: Glimmer (local, effort low) (partial coverage) | `7a1fa761db4d` | structure_schema | bm25 | 1000 | None | 56/69 = 0.811594 | 60994/69 = 883.971014 | False |
| Header B: Glimmer (local, effort low) (partial coverage) | `a74301e77957` | structure_schema | dense | 1000 | None | 1/1 = 1.000000 | 61403/69 = 889.898551 | False |
| Header B: Glimmer (local, effort low) (partial coverage) | `68e2694711a6` | structure_schema | hybrid | 1000 | None | 21/23 = 0.913043 | 20614/23 = 896.260870 | True |
| Header B: Glimmer (local, effort low) (partial coverage) | `6c281c1be364` | structure_handwritten | bm25 | 2000 | None | 0/1 = 0.000000 | 0/1 = 0.000000 | False |
| Header B: Glimmer (local, effort low) (partial coverage) | `d2507439a039` | structure_handwritten | hybrid | 2000 | None | 0/1 = 0.000000 | 0/1 = 0.000000 | False |
| Header B: Glimmer (local, effort low) (partial coverage) | `d4420f51b980` | structure_handwritten | dense | 2000 | None | 0/1 = 0.000000 | 0/1 = 0.000000 | False |
| Header B: Glimmer (local, effort low) (partial coverage) | `033449e79b68` | structure_schema | dense | 2000 | None | 1/1 = 1.000000 | 128626/69 = 1864.144928 | False |
| Header B: Glimmer (local, effort low) (partial coverage) | `2613b50cc4a1` | structure_schema | hybrid | 2000 | None | 67/69 = 0.971014 | 42929/23 = 1866.478261 | True |

## Frontier (main off series + this comparison's header-on points)

- split None budget 1000: `10fab4d684ca` (Header B: Glimmer (local, effort low)), `218bd4731027` (main, header off), `3fa7201e820a` (Header B: Glimmer (local, effort low)), `82ed8c5a7f98` (Header B: Glimmer (local, effort low)), `b6591dd2a76f` (main, header off), `c06630c0a295` (main, header off), `398e53750aea` (main, header off), `7a1fa761db4d` (Header B: Glimmer (local, effort low)), `a74301e77957` (Header B: Glimmer (local, effort low))
- split None budget 2000: `478bc82d2040` (main, header off), `6c281c1be364` (Header B: Glimmer (local, effort low)), `970fb589ecbc` (main, header off), `d2507439a039` (Header B: Glimmer (local, effort low)), `d4420f51b980` (Header B: Glimmer (local, effort low)), `e3a15b5cfc24` (main, header off), `ccc58395c9ed` (main, header off), `033449e79b68` (Header B: Glimmer (local, effort low))

## Failed settings

| Setting | Reason | Chunk |
|---|---|---|
| `b79ded9fb8b1` | header_missing | 6c1d6ad04183411782671bd40856a051724079945cef54f93afe9e85d0a6ebe4 |
| `bab6da76c37c` | header_missing | 6c1d6ad04183411782671bd40856a051724079945cef54f93afe9e85d0a6ebe4 |
