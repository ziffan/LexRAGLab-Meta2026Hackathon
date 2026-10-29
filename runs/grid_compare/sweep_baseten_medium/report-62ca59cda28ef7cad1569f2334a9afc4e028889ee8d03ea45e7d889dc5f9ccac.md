# Header B: Spark Open (Baseten, effort medium) (uupt)

- key: `62ca59cda28ef7cad1569f2334a9afc4e028889ee8d03ea45e7d889dc5f9ccac`; main off series: `runs/grid/e7ffa7b09a60921f408a89fcb3fe8bdd8ed35cd5aadeaf365f78d5b97450a114.json` (key `e7ffa7b09a60921f408a89fcb3fe8bdd8ed35cd5aadeaf365f78d5b97450a114`)
- provider `baseten`, model `meta-models/muse-spark-open-1026`, quantization `None`, effort `medium`
- sources run: pasal, fixed_size, structure_schema; sources not run: (none)
- Not a reported number: comparison only (H-028); the main grid, frontier and selected profile stay Contributor.

## Points (header-on twins)

| Series | Setting | Chunker | Mode | Budget | Split | Span recall | Mean retrieved tokens | Dominated |
|---|---|---|---|---|---|---|---|---|
| Header B: Spark Open (Baseten, effort medium) (partial header coverage 96,44%) | `a2c1286abe38` | structure_handwritten | dense | 1000 | held_out | 1271/1272 = 0.999214 | 6977/8 = 872.125000 | False |
| Header B: Spark Open (Baseten, effort medium) (partial header coverage 96,44%) | `a2c1286abe38` | structure_handwritten | dense | 1000 | tune | 61970023/62036975 = 0.998921 | 9835/11 = 894.090909 | True |

## Frontier (main off series + this comparison's header-on points)

- split held_out budget 1000: `648ddfb1ccc1` (main, header off), `90ca0a269006` (main, header off), `b1b31934c423` (main, header off), `a2c1286abe38` (Header B: Spark Open (Baseten, effort medium))
- split held_out budget 2000: `a801296d2181` (main, header off), `ed489a1ecd83` (main, header off), `a44cd7327ebe` (main, header off)
- split tune budget 1000: `90ca0a269006` (main, header off), `648ddfb1ccc1` (main, header off), `89cd4ddcd09e` (main, header off), `69f43cf1818d` (main, header off), `b1b31934c423` (main, header off)
- split tune budget 2000: `ed489a1ecd83` (main, header off), `21ce1677a270` (main, header off), `1109773ec23a` (main, header off), `d7a9dd244260` (main, header off)

## Failed settings

| Setting | Reason | Chunk |
|---|---|---|
| `f9c814f45fdf` | header_missing | e16748acac3cc13a9c1c555164220bfed00ae5f8acc3d45a07783cf1b715129a |
| `4c627367403d` | header_missing | e16748acac3cc13a9c1c555164220bfed00ae5f8acc3d45a07783cf1b715129a |
| `2ceb42519bc6` | header_missing | e16748acac3cc13a9c1c555164220bfed00ae5f8acc3d45a07783cf1b715129a |
| `6536bfa81b23` | header_missing | e16748acac3cc13a9c1c555164220bfed00ae5f8acc3d45a07783cf1b715129a |
| `c77d06ef4830` | header_missing | bc024383fabc5d40f3f8b43de3fae7651926112df1d8334513f92e5d910f9505 |
| `2aa9f4ac3d3b` | header_missing | bc024383fabc5d40f3f8b43de3fae7651926112df1d8334513f92e5d910f9505 |
| `f26b45c34b9f` | header_missing | bc024383fabc5d40f3f8b43de3fae7651926112df1d8334513f92e5d910f9505 |
| `eb8b3a829415` | header_missing | bc024383fabc5d40f3f8b43de3fae7651926112df1d8334513f92e5d910f9505 |
