# How to run

Commands are for Windows **cmd**. They work the same in PowerShell and in a macOS/Linux terminal;
only the `cd` line differs.

## 1. Requirements

* Python **3.10 or newer**. Nothing else is needed to generate and validate the data.
* `pytest` is only needed for the tests.

Check Python:

```cmd
python --version
```

If this prints `Python 3.x.x`, you are ready. If it opens the Microsoft Store or prints nothing,
`python` is the Windows Store placeholder. Use your real install for this window instead:

```cmd
set PATH=C:\Python314;C:\Python314\Scripts;%PATH%
python --version
```

(`C:\Python314` is an example. Replace it with your Python folder. You can also type the full path,
`C:\Python314\python.exe`, wherever this guide says `python`.)

## 2. Run everything (one command)

```cmd
cd /d "<path-to-repo>"
python -m procurement_synth all
```

This generates the **starter** (10%) and **full** datasets, validates both, checks that two runs
give identical files, and rebuilds `docs/data_dictionary.md`. It takes about 10 seconds.

Expected output (row counts are printed first for each scale):

```
generated starter (seed 20261022) -> ...\data\starter
  ...
validation PASS: 547 checks, 0 failing
reproducibility starter: identical across 58 files
  shipped data/starter matches: 58/58 files
generated full (seed 20261022) -> ...\data\full
  purchase_request              1200
  rfq                            500
  supplier_quote                1500
  purchase_order                 918
  ...
  ground truth labels             65
validation PASS: 547 checks, 0 failing
reproducibility full: identical across 58 files
  shipped data/full matches: 58/58 files
```

Success means: both lines say `validation PASS` and `identical`, and the command exits with no error.

## 3. Run the tests

```cmd
python -m pip install pytest
python -m pytest -q
```

Expected: `9 passed`.

## Running it again

Running `python -m procurement_synth all` again when the data already exists is safe:

* For each scale it **deletes and rebuilds** `csv\`, `json\`, `sql\` and `ground_truth\`, and
  **overwrites** `manifest.json`, the files in `reports\` and `docs\data_dictionary.md`.
* The seed is fixed, so every file comes out **byte-identical**. Only the file dates change, and
  `git status` stays clean.
* **Lost on re-run:** hand edits to any CSV/JSON/SQL file, and any extra file you put inside
  `csv\`, `json\`, `sql\` or `ground_truth\`. Extra files in `reports\` are kept.
* **Close Excel first.** A CSV open in Excel is locked, and the run fails with `PermissionError`.
* `all --seed 7` (any other seed) replaces the data with different data. To get the original back,
  run `python -m procurement_synth all` again, or `git checkout -- data docs`.

`python -m pytest -q` never touches `data\`. The tests build their own datasets in the system
temp folder, so you can run them any number of times.

## Run steps one at a time (optional)

| What | Command | Writes to |
|---|---|---|
| Generate full dataset | `python -m procurement_synth generate --scale full` | `data\full\` |
| Generate starter dataset | `python -m procurement_synth generate --scale starter` | `data\starter\` |
| Clean data, no injected anomalies | `python -m procurement_synth generate --scale full --no-anomalies --out C:\temp\clean` | `C:\temp\clean\` |
| Use another seed | `python -m procurement_synth generate --scale full --seed 7 --out C:\temp\seed7` | `C:\temp\seed7\` |
| Validate a dataset | `python -m procurement_synth validate --data data\full` | `data\full\reports\` |
| Reproducibility check | `python -m procurement_synth reproduce --scale full` | `data\full\reports\reproducibility.*` |
| Rebuild data dictionary | `python -m procurement_synth docs` | `docs\data_dictionary.md` |
| Help | `python -m procurement_synth --help` | nothing |

## Run without touching the repository

`all`, `generate` (without `--out`), `validate --data data\...`, `reproduce` and `docs` overwrite
files inside the repo. With the default seed the new files are byte-identical to the committed
ones, so `git status` stays clean. To keep the repo completely untouched, write to another folder:

```cmd
python -m procurement_synth generate --scale full --out C:\temp\p2p
python -m procurement_synth validate --data C:\temp\p2p
```

## Where the results are

```
data\<starter|full>\
  csv\            27 tables as CSV
  json\           same tables as JSON
  sql\            schema.sql (tables, keys) and seed.sql (inserts)
  ground_truth\   labelled anomalies (CSV and JSON)
  manifest.json   seed, row counts, SHA-256 per file
  reports\        validation_summary.md, metrics.md, control_findings.csv,
                  baseline_check.json, reproducibility.md
```

Start with `data\full\reports\validation_summary.md` and `data\full\reports\metrics.md`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` opens the Microsoft Store | See step 1: `set PATH=...` or use the full path to `python.exe`. |
| `No module named procurement_synth` | You are not in the project folder. Run the `cd /d ...` line first. |
| `No module named pytest` | `python -m pip install pytest` |
| Python older than 3.10 | Install Python 3.10+ from python.org. |
