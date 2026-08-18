#!/usr/bin/env python3
"""HindSweep - run Hindsight against every browser profile found under a root directory.

Usage (after editing hindsweep_config.json once):
    python hindsweep.py -i <root>
    python hindsweep.py -i <root> -o my_case
    python hindsweep.py --list-only -i <root>
"""

import sys

if sys.version_info < (3, 11):
    sys.exit(f'HindSweep needs Python 3.11+ (Hindsight itself uses datetime.UTC, added in 3.11). '
             f'"{sys.executable}" is {sys.version.split()[0]}. Try "python3" instead of "python", '
             f'or point at a newer interpreter.')

import argparse
import csv
import hashlib
import json
import os
import subprocess
import time

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(SCRIPT_DIR, 'hindsweep_config.json')

BUILT_IN_DEFAULTS = {
    'hindsight_path': '../hindsight/hindsight.py',
    'timezone': 'Asia/Jakarta',
    'format': 'csv',
    'decrypt': None,
    'nocopy': False,
    'default_prefix': 'test_case',
    'default_root': None,
    'browsers': None,
    'output_name_template': '{prefix}_{browser}',
    'output_dir_template': '{prefix}_output',
}

# Mirrors pyhindsight.analysis.AnalysisSession's own profile detection rules,
# duplicated here so enumeration only needs the standard library.
MARKER_FILES = {'History': 'Chrome', 'places.sqlite': 'Firefox'}
CHROMIUM_VARIANT_PREFS_KEYS = (('edge', 'Edge'), ('brave', 'Brave'), ('vivaldi', 'Vivaldi'))
TOR_PREFS_MARKERS = ('torbrowser.', 'extensions.torbutton', 'extensions.torlauncher')
PRUNE_DIR_NAMES = {'node_modules', '.git', '$recycle.bin', 'system volume information'}


def load_config(path):
    config = dict(BUILT_IN_DEFAULTS)
    if path and os.path.isfile(path):
        try:
            with open(path, encoding='utf-8') as f:
                config.update(json.load(f))
        except ValueError as e:
            sys.exit(f'Error: "{path}" is not valid JSON ({e}).')
    elif path:
        print(f'Warning: config file "{path}" not found; using built-in defaults.', file=sys.stderr)
    return config


def default_live_root():
    if sys.platform.startswith('win'):
        return os.path.join(os.environ.get('SystemDrive', 'C:'), '\\Users')
    if sys.platform == 'darwin':
        return '/Users'
    return '/home'


def is_profile_dir(filenames):
    for marker, family in MARKER_FILES.items():
        if marker in filenames:
            return family
    return None


def detect_variant(dirpath, filenames, family):
    if family == 'Chrome':
        if 'Preferences' in filenames:
            try:
                with open(os.path.join(dirpath, 'Preferences'), encoding='utf-8') as f:
                    prefs = json.load(f)
                if isinstance(prefs, dict):
                    for key, variant in CHROMIUM_VARIANT_PREFS_KEYS:
                        if key in prefs:
                            return variant
            except (OSError, ValueError):
                pass
        return 'Chrome'

    if family == 'Firefox':
        if 'prefs.js' in filenames:
            try:
                with open(os.path.join(dirpath, 'prefs.js'), encoding='utf-8', errors='replace') as f:
                    prefs_text = f.read()
                if any(marker in prefs_text for marker in TOR_PREFS_MARKERS):
                    return 'Tor'
            except OSError:
                pass
        return 'Firefox'

    return family


def guess_username(profile_path):
    # Scan from the end: the marker closest to the profile is the one that
    # actually names its owner. An earlier match is often just the analyst's
    # own path (e.g. a KAPE collection extracted under their own home dir).
    parts = profile_path.replace('\\', '/').split('/')
    markers = {'users', 'home'}
    for i in range(len(parts) - 2, -1, -1):
        if parts[i].lower() in markers:
            return parts[i + 1]
    digest = hashlib.md5(profile_path.encode('utf-8')).hexdigest()[:6]
    return f'p{digest}'


def find_profiles(root, browsers_filter=None):
    profiles = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
        dirnames[:] = [d for d in dirnames if d.lower() not in PRUNE_DIR_NAMES]
        family = is_profile_dir(filenames)
        if not family:
            continue
        variant = detect_variant(dirpath, filenames, family)
        if browsers_filter and variant.lower() not in browsers_filter:
            continue
        profiles.append({
            'path': dirpath,
            'browser': variant,
            'user': guess_username(dirpath),
        })
    return profiles


def build_output_names(prefix, template, profiles):
    names = []
    used = set()
    for profile in profiles:
        base = template.format(prefix=prefix, browser=profile['browser'].lower(), user=profile['user'])
        name = base
        if name in used:
            name = f"{base}_{profile['user']}"
        n = 2
        while name in used:
            name = f"{base}_{n}"
            n += 1
        used.add(name)
        names.append(name)
    return names


def check_csv_dependencies():
    # csv isn't a Hindsight output format; HindSweep converts xlsx itself,
    # which needs pandas/openpyxl on top of Hindsight's own requirements.
    try:
        import pandas  # noqa: F401
        import openpyxl  # noqa: F401
    except ImportError as e:
        sys.exit(f'Error: --format csv needs pandas and openpyxl ({e}). Install with: '
                 f'"{sys.executable}" -m pip install pandas openpyxl')


def convert_xlsx_to_csv(xlsx_path, base_output_path):
    # Hindsight's xlsx has one sheet per artifact type (Timeline, Chrome
    # Preferences, ...); write each sheet to its own CSV. Ported from an
    # xlsx-to-csv script by Nicolas Saputra Gunawan (github.com/jon-brandy).
    import pandas as pd

    # row 0 of every Hindsight sheet is a title/section-group row, not
    # column headers; the real headers are on row 1.
    sheets = pd.read_excel(xlsx_path, sheet_name=None, header=1, engine='openpyxl')
    written = []
    for sheet_name, df in sheets.items():
        clean_name = ''.join(c for c in sheet_name if c.isalnum() or c in (' ', '-', '_')).strip()
        csv_path = f'{base_output_path}_{clean_name}.csv'
        df.to_csv(csv_path, index=False)
        written.append(csv_path)
    return written


def run_hindsight(hindsight_path, profile, output_path, config, log_path):
    # hindsight_path may be the .py script (needs this interpreter) or a
    # packaged binary like hindsight.exe (runs on its own).
    launcher = [sys.executable, hindsight_path] if hindsight_path.lower().endswith('.py') else [hindsight_path]
    # Hindsight itself only knows xlsx/jsonl/sqlite; for csv, have it write
    # xlsx and convert that afterward.
    hindsight_format = 'xlsx' if config['format'] == 'csv' else config['format']
    cmd = [
        *launcher,
        '-i', profile['path'],
        '-o', output_path,
        '-b', profile['browser'].lower(),
        '-t', config['timezone'],
        '-f', hindsight_format,
        '-l', log_path,
    ]
    if config.get('decrypt'):
        cmd += ['-d', config['decrypt']]
    if config.get('nocopy'):
        cmd.append('--nocopy')

    start = time.time()
    try:
        result = subprocess.run(cmd, stdin=subprocess.DEVNULL)
        success = result.returncode == 0
    except OSError as e:
        print(f'  Failed to launch hindsight: {e}', file=sys.stderr)
        success = False
    elapsed = time.time() - start

    output_files = []
    if success and config['format'] == 'csv':
        xlsx_path = f'{output_path}.xlsx'
        try:
            output_files = convert_xlsx_to_csv(xlsx_path, output_path)
            os.remove(xlsx_path)
        except Exception as e:
            print(f'  CSV conversion failed: {e}', file=sys.stderr)
            success = False
    elif success:
        output_files = [f"{output_path}.{config['format']}"]

    return success, elapsed, output_files


def parse_arguments():
    parser = argparse.ArgumentParser(description='Run Hindsight against every browser profile found under a root.')
    parser.add_argument('-i', '--root', help='Root directory to search for browser profiles '
                                              '(mounted image, KAPE output, etc). Defaults to a live scan of '
                                              "this machine's user directories if omitted.")
    parser.add_argument('-o', '--prefix', help='Output/case name prefix')
    parser.add_argument('-t', '--timezone', help='Display timezone for output timestamps')
    parser.add_argument('-f', '--format', choices=['csv', 'xlsx', 'jsonl', 'sqlite'], help='Output format')
    parser.add_argument('-d', '--decrypt', choices=['mac', 'linux'], help='Try to decrypt data from a Mac/Linux system')
    parser.add_argument('--nocopy', action='store_true', default=None, help="Don't copy files before opening them")
    parser.add_argument('--browsers', help='Comma-separated list of browsers to include (e.g. chrome,firefox)')
    parser.add_argument('--hindsight-path', help='Path to hindsight.py or hindsight.exe')
    parser.add_argument('--config', default=DEFAULT_CONFIG_PATH, help='Path to config JSON file')
    parser.add_argument('--output-dir', help='Directory to write outputs into')
    parser.add_argument('--list-only', action='store_true', help='List discovered profiles and planned output names without running Hindsight')
    return parser.parse_args()


def main():
    args = parse_arguments()
    config = load_config(args.config)

    root = args.root or config['default_root'] or default_live_root()
    prefix = args.prefix or config['default_prefix']
    config['timezone'] = args.timezone or config['timezone']
    config['format'] = args.format or config['format']
    config['decrypt'] = args.decrypt or config['decrypt']
    config['nocopy'] = args.nocopy if args.nocopy is not None else config['nocopy']

    browsers_filter = None
    browsers_arg = args.browsers if args.browsers is not None else config['browsers']
    if browsers_arg:
        browsers_filter = {b.strip().lower() for b in browsers_arg.split(',') if b.strip()}

    hindsight_path = args.hindsight_path or config['hindsight_path']
    if not os.path.isabs(hindsight_path):
        hindsight_path = os.path.normpath(os.path.join(SCRIPT_DIR, hindsight_path))
    if not os.path.isfile(hindsight_path):
        print(f'Error: hindsight.py/hindsight.exe not found at "{hindsight_path}". '
              f'Set "hindsight_path" in {args.config} or pass --hindsight-path.', file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(root):
        print(f'Error: root directory "{root}" does not exist.', file=sys.stderr)
        sys.exit(1)

    output_dir = args.output_dir or config['output_dir_template'].format(prefix=prefix)
    output_dir = os.path.abspath(output_dir)

    if config['format'] == 'csv' and not args.list_only:
        check_csv_dependencies()

    print(f'Scanning "{root}" for browser profiles...')
    profiles = find_profiles(root, browsers_filter)

    if not profiles:
        print('No browser profiles found.')
        sys.exit(0)

    output_names = build_output_names(prefix, config['output_name_template'], profiles)

    print(f'Found {len(profiles)} profile(s):')
    for profile, name in zip(profiles, output_names):
        dest = f'{name}_<sheet>.csv (one file per sheet)' if config['format'] == 'csv' else f"{name}.{config['format']}"
        print(f"  - {profile['browser']:<8} {profile['path']}  ->  {dest}")

    if args.list_only:
        print('\nList-only: no profiles were processed.')
        sys.exit(0)

    os.makedirs(output_dir, exist_ok=True)
    log_path = os.path.join(output_dir, 'hindsight.log')

    summary_rows = []
    print()
    for idx, (profile, name) in enumerate(zip(profiles, output_names), start=1):
        print(f'[{idx}/{len(profiles)}] {profile["browser"]} - {profile["path"]}')
        output_path = os.path.join(output_dir, name)
        success, elapsed, output_files = run_hindsight(hindsight_path, profile, output_path, config, log_path)
        status = 'success' if success else 'failed'
        print(f'  -> {status} ({elapsed:.1f}s)\n')
        summary_rows.append({
            'profile_path': profile['path'],
            'browser': profile['browser'],
            'output_name': '; '.join(os.path.basename(p) for p in output_files),
            'status': status,
            'elapsed_seconds': f'{elapsed:.1f}',
        })

    summary_path = os.path.join(output_dir, f'{prefix}_run_summary.csv')
    with open(summary_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['profile_path', 'browser', 'output_name', 'status', 'elapsed_seconds'])
        writer.writeheader()
        writer.writerows(summary_rows)

    succeeded = sum(1 for row in summary_rows if row['status'] == 'success')
    print(f'Done: {succeeded}/{len(summary_rows)} profiles processed successfully.')
    print(f'Outputs: {output_dir}')
    print(f'Summary: {summary_path}')


if __name__ == '__main__':
    main()
