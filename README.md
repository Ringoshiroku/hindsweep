# HindSweep

HindSweep is a single Python script that runs [Hindsight](https://github.com/RyanDFIR/hindsight)
against every browser profile it finds under a directory, instead of you
invoking `hindsight.py` by hand once per Chrome/Edge/Brave/Vivaldi/Firefox/Tor
profile. Point it at a mounted image, a KAPE collection, or (if you leave the
path off) this machine's own user directories, and it finds every profile,
runs Hindsight on each one, and writes a run summary. It has no server-side
component and doesn't parse anything itself: it drives Hindsight, which does
the real parsing.

## Requirements

- Python 3.11+. Run it with whichever command your OS uses for Python 3:
  `python` on Windows, `python3` on Linux/macOS. Either works the same here
  (HindSweep just re-uses whatever interpreter launched it to run Hindsight
  too) — it only matters that the command you use actually points at Python
  3.11+; HindSweep checks and errors clearly if it doesn't. (Note:
  Hindsight's own `setup.py` currently claims `>=3.9`, but its code uses
  `datetime.UTC`, which only exists from 3.11 onward — so 3.11+ is what
  actually works, whatever Hindsight's packaging metadata says.) The
  examples below use `python`; swap in `python3` on Linux/macOS.
- `pandas` and `openpyxl`, only if you use the default `csv` output format
  (`pip install pandas openpyxl`). Hindsight has no native CSV output
  (just xlsx/jsonl/sqlite), so for `csv` HindSweep has Hindsight write xlsx
  and then converts it itself. The `xlsx`/`jsonl`/`sqlite` formats don't
  need these — HindSweep otherwise only uses the standard library.
- Hindsight, cloned or downloaded, with its own dependencies installed:
  ```sh
  git clone https://github.com/RyanDFIR/hindsight.git
  cd hindsight
  pip install -r requirements.txt
  ```
  A downloaded release build (`hindsight.exe`) works too, no Python
  environment needed for it, just point `hindsight_path` in the config
  (below) at it. HindSweep detects which kind it's calling from the file
  extension: a `.py` path is run with the same Python that's running
  HindSweep, anything else (e.g. `hindsight.exe`) is launched directly.
  HindSweep expects `../hindsight/hindsight.py` next to itself by default,
  i.e. `hindsight/` and this `hindsweep/` folder as sibling directories.

## Getting started

1. Make sure Hindsight is installed and runs on its own first (see
   [Requirements](#requirements)).
2. Copy `hindsweep_config.example.json` to `hindsweep_config.json` and fill
   in `hindsight_path` (if it isn't already a sibling `hindsight/` folder)
   and `timezone`. Everything else has a sensible default and rarely needs
   to change. `hindsweep_config.json` is your own local config (gitignored,
   not tracked); only the `.example.json` template is committed.
3. Run it against a root directory:
   ```sh
   python hindsweep.py -i "G:\Project\WorkstationA\KAPE\F"   # macOS/Linux: python3 instead of python
   ```
   Every later run only needs `-i` (and optionally `-o` for a case name);
   the rest comes from `hindsweep_config.json`.

## Quick commands

On macOS/Linux, replace `python` with `python3` below.

```sh
# Preview what would be processed, without running Hindsight
python hindsweep.py --list-only -i "G:\Project\WorkstationA\KAPE\F"

# Process everything found under a root, using config defaults
python hindsweep.py -i "G:\Project\WorkstationA\KAPE\F"

# Same, with a custom case name prefix
python hindsweep.py -i "G:\Project\WorkstationA\KAPE\F" -o case001

# No -i: scans this machine's own user directories (C:\Users, /home, /Users)
python hindsweep.py -o case001

# Only sweep specific browsers
python hindsweep.py -i "G:\Project\WorkstationA\KAPE\F" --browsers chrome,firefox
```

## Parameters

| Flag | Required | Default | Purpose |
|---|---|---|---|
| `-i`, `--root` | no | live scan of this machine's user directories | directory to search for browser profiles (mounted image, KAPE output, etc.) |
| `-o`, `--prefix` | no | `default_prefix` from config (`test_case`) | output/case name prefix |
| `-t`, `--timezone` | no | `timezone` from config | display timezone for output timestamps |
| `-f`, `--format` | no | `format` from config (`csv`) | `csv`, `xlsx`, `jsonl`, or `sqlite`. `csv` has Hindsight write xlsx, then converts every sheet to its own CSV per profile and deletes the intermediate xlsx (needs `pandas`/`openpyxl`, see [Requirements](#requirements)) |
| `-d`, `--decrypt` | no | `decrypt` from config (off) | `mac` or `linux`, passed straight to Hindsight |
| `--nocopy` | no | `nocopy` from config (off) | don't copy files before opening them |
| `--browsers` | no | `browsers` from config (all) | comma-separated list to restrict to, e.g. `chrome,firefox` |
| `--hindsight-path` | no | `hindsight_path` from config | path to `hindsight.py` or `hindsight.exe` |
| `--output-dir` | no | `output_dir_template` from config (`<prefix>_output`) | where results are written |
| `--config` | no | `hindsweep_config.json` next to the script | path to a different config file |
| `--list-only` | no | off | list discovered profiles and planned output names, don't run Hindsight |

A flag passed on the command line always overrides the config file.

## What each run does

1. Resolves the root (from `-i`, or `default_root` in config, or a live scan
   of this OS's user directories) and walks it looking for the same markers
   Hindsight itself uses per profile (`History` for Chromium-family browsers,
   `places.sqlite` for Firefox/Tor), refining the exact browser from
   `Preferences`/`prefs.js`.
2. Builds a collision-safe output name per profile from
   `output_name_template` (default `<prefix>_<browser>`; the username is
   appended automatically only if two profiles would otherwise share a name).
3. Unless `--list-only` was passed, runs `hindsight.py` once per profile with
   the resolved timezone/format/decrypt/nocopy settings, forcing `-b` to the
   browser it already detected. For `csv`, Hindsight is told to write `xlsx`;
   on success, HindSweep converts every sheet in that xlsx to its own CSV
   file and deletes the xlsx (if conversion fails, the xlsx is kept and the
   profile is marked failed instead). One profile failing doesn't stop the
   rest.
4. Writes every output file plus `<prefix>_run_summary.csv` (profile path,
   browser, output file(s), success/failure, elapsed time) and
   `hindsight.log` into the output directory.

## Local files

| File | Purpose |
|---|---|
| `hindsweep_config.example.json` | committed template; copy to `hindsweep_config.json` to start |
| `hindsweep_config.json` | your local settings (gitignored); fill in before your first run |
| `<prefix>_output/` | Hindsight output per profile (one file, or with the default `csv` format, one CSV per sheet), plus the run summary and log for that run |
