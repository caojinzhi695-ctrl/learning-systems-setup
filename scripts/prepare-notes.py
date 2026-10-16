"""Apply the pinned note customization without copying private installation state."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

PACKAGE = Path(__file__).resolve().parents[1] / 'customizations' / 'DeepTutor'


def git(source, *args, check=True):
    result = subprocess.run(['git', '-C', str(source), *args], capture_output=True)
    if check and result.returncode:
        raise SystemExit('Git check failed; no blind overwrite. ' + result.stderr.decode('utf-8', errors='replace'))
    return result


def child(root, relative):
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()):
        raise SystemExit('Unsafe package path rejected.')
    return result


def apply(source, dry_run=False):
    source = source.resolve()
    manifest = json.loads((PACKAGE / 'manifest.json').read_text(encoding='utf-8'))
    head = git(source, 'rev-parse', 'HEAD').stdout.decode().strip()
    if head != manifest['base_commit']:
        raise SystemExit('This package only supports DeepTutor ' + manifest['version'] + '; no files changed.')
    patch = PACKAGE / 'tracked.patch'
    if hashlib.sha256(patch.read_bytes()).hexdigest() != manifest['patch_sha256']:
        raise SystemExit('Patch checksum mismatch; no files changed.')
    upgrades = []
    for name, expected in manifest['files'].items():
        payload, target = child(PACKAGE / 'files', name), child(source, name)
        if hashlib.sha256(payload.read_bytes()).hexdigest() != expected:
            raise SystemExit('Payload checksum mismatch: ' + name)
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual not in manifest.get('previous_files', {}).get(name, []):
                raise SystemExit('Existing customized file differs; back up and merge manually: ' + name)
            upgrades.append(name)
    already = git(source, 'apply', '--reverse', '--check', str(patch), check=False).returncode == 0
    if not already:
        git(source, 'apply', '--check', str(patch))
    if dry_run:
        print('Dry run passed: pinned version, payload checksums and patch compatibility verified.')
        return
    if upgrades:
        upgrade_backup = source.parent / 'backups' / ('notes-upgrade-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        for name in upgrades:
            saved = child(upgrade_backup, name)
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child(source, name), saved)
    if not already:
        backup = source.parent / 'backups' / ('notes-code-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        for name in manifest['patched_files']:
            target = child(backup, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child(source, name), target)
        git(source, 'apply', str(patch))
    for name in manifest['files']:
        target = child(source, name)
        if not target.exists() or name in upgrades:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child(PACKAGE / 'files', name), target)
    print('Pinned summary-notes customization ready. Private settings and learning data were not copied or changed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    apply(args.source, args.dry_run)
