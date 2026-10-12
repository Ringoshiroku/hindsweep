# HindSweep

HindSweep is a single Python script that runs [Hindsight](https://github.com/RyanDFIR/hindsight)
against every browser profile it finds under a folder (Chrome, Edge, Brave,
Vivaldi, Firefox, Tor), instead of you running `hindsight.py` by hand once
per profile. It has no server-side component and doesn't parse anything
itself: Hindsight does the parsing, HindSweep finds the profiles and fills in
the right options for each one. See [Basic usage](#basic-usage).

It works the same on Windows, Linux and macOS, against a mounted image, a
KAPE collection, or the live machine, and evidence from one OS can be swept
from another. See [Linux and macOS](#linux-and-macos) for what it handles
automatically there.

## Requirements

- Python 3.11+ (`python` on Windows, `python3` on Linux/macOS). Hindsight
  needs 3.11 too, whatever its packaging says.
- Hindsight with its dependencies installed. HindSweep expects it in a
  sibling folder (`../hindsight/hindsight.py`) by default:
  ```sh
  git clone https://github.com/RyanDFIR/hindsight.git
  pip install -r hindsight/requirements.txt
  ```
  A release binary (`hindsight.exe`, or a Linux/macOS build marked
  executable) works too, point `hindsight_path` at it.
- `pandas` and `openpyxl` for the default `csv` output only
  (`pip install pandas openpyxl`). Hindsight can't write CSV itself, so
  HindSweep converts its xlsx output. Other formats need nothing extra.

## Built-in help

```sh
python hindsweep.py -h
```

## Getting started

1. Copy `hindsweep_config.example.json` to `hindsweep_config.json`.
2. Set `timezone`, and `hindsight_path` if Hindsight isn't in a sibling
   `hindsight/` folder. Everything else has a working default.
3. Preview what would be processed, then run it:
   ```sh
   python hindsweep.py --list-only -i "G:\Case\KAPE\F"
   python hindsweep.py -i "G:\Case\KAPE\F" -o case001
   ```

Every later run only needs `-i` and optionally `-o`; the rest comes from
`hindsweep_config.json`. A flag on the command line always overrides the
config.

## Basic usage

```sh
python hindsweep.py -i "G:\Case\KAPE\F"                     # a Windows collection
python3 hindsweep.py -i /mnt/evidence/ubuntu -o case002     # a mounted Linux/macOS image
python hindsweep.py -o case003                              # live: this machine's user folders
sudo python3 hindsweep.py -o case003                        # live Linux, including /root
python hindsweep.py -i "G:\Case\KAPE\F" --browsers chrome,firefox
```

With no `-i`, HindSweep scans this machine's user folders: `C:\Users` on
Windows, `/home` and `/root` on Linux, `/Users` and `/var/root` on macOS. A
folder it can't read (usually `/root` without `sudo`) is skipped with a
warning.

## Parameters

| Flag | Required | Default | Purpose |
|---|---|---|---|
| `-i`, `--root` | no | live scan | folder to search for browser profiles |
| `-o`, `--prefix` | no | `test_case` | case name, used for output file and folder names |
| `-t`, `--timezone` | no | from config | display timezone for output timestamps |
| `-f`, `--format` | no | `csv` | `csv` (one CSV per Hindsight sheet), `xlsx`, `jsonl`, or `sqlite` |
| `-d`, `--decrypt` | no | `auto` | `auto` picks per profile, see [Linux and macOS](#linux-and-macos); `none`, `mac` or `linux` applies to every profile |
| `--nocopy` | no | off | don't copy files before opening them |
| `--browsers` | no | all | comma-separated list, e.g. `chrome,firefox` |
| `--hindsight-path` | no | `../hindsight/hindsight.py` | path to `hindsight.py` or a release binary |
| `--output-dir` | no | `<prefix>_output` | where results are written |
| `--config` | no | `hindsweep_config.json` | a different config file |
| `--list-only` | no | off | list the profiles found and their output names, don't run Hindsight |

## What each run does

1. Walks the folder for the same files Hindsight uses to spot a profile
   (`History` for Chromium browsers, `places.sqlite` for Firefox/Tor), and
   reads `Preferences`/`prefs.js` to tell Edge, Brave, Vivaldi and Tor apart.
2. Tags each profile with the OS it came from, based on its path, and works
   out the Hindsight options it needs (see [Linux and macOS](#linux-and-macos)).
3. Runs Hindsight once per profile. One profile failing doesn't stop the
   rest. Output is named `<prefix>_<browser>`, with the username added only
   if two profiles would clash.
4. Writes a `<prefix>_run_summary.csv` (profile, browser, source OS, options
   used, output files, success/failure, time taken) and `hindsight.log`
   next to the output.

## Linux and macOS

Profiles are found wherever they are, including the default locations
Hindsight lists, snap (`~/snap/...`) and flatpak (`~/.var/app/...`)
installs:

| Source | Default Chrome profile path |
|---|---|
| Windows | `<userdir>\AppData\Local\Google\Chrome\User Data\Default` |
| Linux | `<userdir>/.config/google-chrome/Default` |
| macOS | `<userdir>/Library/Application Support/Google/Chrome/Default` |
| iOS | `/Applications/com.google.chrome.ios/Library/Application Support/Google/Chrome/Default` |
| Android | `/userdata/data/com.android.chrome/app_chrome/Default` |
| ChromeOS | `/home/user/<GUID>` |

Two things differ from Windows, and HindSweep handles both through
Hindsight's own options:

- **Cache**: Linux and macOS keep the browser cache outside the profile
  (`~/.cache/...`, `~/Library/Caches/...`), which Hindsight only reads if
  given `-c`. HindSweep passes it when that folder exists in the evidence.
- **Decryption** (`-d auto`): Chromium profiles from Linux get `-d linux`,
  which works offline from any OS. macOS profiles get `-d mac` only on a live
  scan of that Mac, the only case Hindsight supports. Windows needs nothing
  extra. Hindsight calls its Linux/Mac decryption experimental; use
  `-d none` if it causes trouble.

A config made before this has `"decrypt": null`, which means off. Set it to
`"auto"`.

## Local files

| File | Purpose |
|---|---|
| `hindsweep_config.example.json` | template, copy to `hindsweep_config.json` |
| `hindsweep_config.json` | your local settings (not tracked by git) |
| `<prefix>_output/` | Hindsight output per profile, the run summary, and `hindsight.log` |
