# HindSweep

HindSweep is a single Python script that runs [Hindsight](https://github.com/RyanDFIR/hindsight)
against every browser profile it finds under a directory, instead of you
invoking `hindsight.py` by hand once per Chrome/Edge/Brave/Vivaldi/Firefox/Tor
profile. Point it at a mounted image, a KAPE collection, or (if you leave the
path off) this machine's own user directories, and it finds every profile,
runs Hindsight on each one, and writes a run summary. It has no server-side
component and doesn't parse anything itself: it drives Hindsight, which does
the real parsing.

It runs on Windows, Linux and macOS, and handles evidence from any of them
regardless of which OS you run it on: a Linux image can be swept from
Windows and the reverse. For Linux and macOS profiles it also fills in the
Hindsight options those layouts need (`-c` for the out-of-profile cache,
`-d` for decryption); see [Linux and macOS profiles](#linux-and-macos-profiles).

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
  A downloaded release build (`hindsight.exe`, or a Linux/macOS binary)
  works too, no Python environment needed for it, just point
  `hindsight_path` in the config (below) at it. HindSweep detects which kind
  it's calling from the file extension: a `.py` path is run with the same
  Python that's running HindSweep, anything else (e.g. `hindsight.exe`) is
  launched directly, so on Linux/macOS make sure the binary is executable
  (`chmod +x`).
  HindSweep expects `../hindsight/hindsight.py` next to itself by default,
  i.e. `hindsight/` and this `hindsweep/` folder as sibling directories.
  When running the `.py` script (not needed for `hindsight.exe`), HindSweep
  sets `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8` for it: Hindsight's `rich`
  dependency otherwise crashes trying to render its progress spinner on a
  non-UTF-8 Windows console, which is exactly the non-interactive setup
  HindSweep runs it in.

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

# A mounted Linux or macOS image works the same way
python3 hindsweep.py -i /mnt/evidence/ubuntu_root -o case002

# Same, with a custom case name prefix
python hindsweep.py -i "G:\Project\WorkstationA\KAPE\F" -o case001

# No -i: scans this machine's own user directories
# (C:\Users on Windows, /home and /root on Linux, /Users and /var/root on macOS)
python hindsweep.py -o case001

# Live Linux scan including /root and other users' homes
sudo python3 hindsweep.py -o case001

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
| `-d`, `--decrypt` | no | `decrypt` from config (`auto`) | `auto` picks Hindsight's `-d` per profile (see [Linux and macOS profiles](#linux-and-macos-profiles)); `none` turns it off; `mac` or `linux` passes that value to Hindsight for every profile |
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
   `Preferences`/`prefs.js`. On a live scan, `/proc`, `/sys`, `/dev` and
   `/run` are skipped. Each profile is also tagged with the OS it came from
   (from its path layout), and for Linux/macOS profiles HindSweep looks for
   the out-of-profile cache folder and picks the decrypt mode.
2. Builds a collision-safe output name per profile from
   `output_name_template` (default `<prefix>_<browser>`; the username is
   appended automatically only if two profiles would otherwise share a name).
3. Unless `--list-only` was passed, runs `hindsight.py` once per profile with
   the resolved timezone/format/nocopy settings, forcing `-b` to the browser
   it already detected, plus `-c`/`-d` where step 1 found them. For `csv`, Hindsight is told to write `xlsx`;
   on success, HindSweep converts every sheet in that xlsx to its own CSV
   file and deletes the xlsx (if conversion fails, the xlsx is kept and the
   profile is marked failed instead). One profile failing doesn't stop the
   rest.
4. Writes every output file plus `<prefix>_run_summary.csv` (profile path,
   browser, source OS, cache path and decrypt mode passed to Hindsight,
   output file(s), success/failure, elapsed time) and `hindsight.log` into
   the output directory.

## Linux and macOS profiles

Profile discovery is the same on every OS: HindSweep looks for Hindsight's
marker files, so it finds profiles wherever they are. That includes the
default locations Hindsight lists:

| Source | Default Chrome profile path |
|---|---|
| Windows Vista-11 | `<userdir>\AppData\Local\Google\Chrome\User Data\Default` |
| Windows XP | `<userdir>\Local Settings\Application Data\Google\Chrome\User Data\Default` |
| Linux | `<userdir>/.config/google-chrome/Default` |
| macOS | `<userdir>/Library/Application Support/Google/Chrome/Default` |
| iOS | `/Applications/com.google.chrome.ios/Library/Application Support/Google/Chrome/Default` |
| Android | `/userdata/data/com.android.chrome/app_chrome/Default` |
| ChromeOS | `/home/user/<GUID>` |

It also finds snap (`~/snap/...`) and flatpak (`~/.var/app/...`) installs,
and `/root`. Each profile's source OS (`windows`, `linux`, `mac`, `ios`,
`android`, `chromeos`, or `unknown`) is shown in `--list-only` and in the
run summary.

On Linux and macOS, two things work differently from Windows. HindSweep
handles both through Hindsight's own options and doesn't parse anything
itself:

- **Cache outside the profile.** Linux keeps the browser cache under
  `~/.cache/...` and macOS under `~/Library/Caches/...`, not in the profile
  folder, and Hindsight only parses such a cache when given `-c`. If the
  profile has no cache of its own, HindSweep passes `-c` with the matching
  cache folder, but only when that folder exists in the evidence. This
  covers Chromium-family browsers on Linux/macOS (including snap and
  flatpak) and Firefox on Linux. Hindsight already finds Firefox's cache on
  Windows and macOS by itself, so HindSweep doesn't pass `-c` there.
- **Decryption (`decrypt: auto`).** Chromium-family profiles from Linux get
  `-d linux`; Hindsight decrypts these with Chrome's built-in Linux key, so
  this works offline on any OS. It needs Hindsight's `pycryptodomex`
  dependency, and only works for data that wasn't protected by the user's
  desktop keyring (`v11`). macOS profiles get `-d mac` only on a live scan
  run on that Mac, because Hindsight reads the key from the local Keychain.
  Hindsight decrypts Windows data by itself when run on the live Windows
  machine; HindSweep passes nothing extra for it. Hindsight describes its
  Linux/Mac decryption as experimental, so if it causes trouble, set
  `decrypt` to `none` (or pass `-d none`).

Older copies of `hindsweep_config.json` have `"decrypt": null`, which still
means off. Change it to `"auto"` to get the behaviour above.

## Local files

| File | Purpose |
|---|---|
| `hindsweep_config.example.json` | committed template; copy to `hindsweep_config.json` to start |
| `hindsweep_config.json` | your local settings (gitignored); fill in before your first run |
| `<prefix>_output/` | Hindsight output per profile (one file, or with the default `csv` format, one CSV per sheet), plus the run summary and log for that run |
