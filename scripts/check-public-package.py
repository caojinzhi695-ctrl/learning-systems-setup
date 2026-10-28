"""Offline checks for distributable source, exact hashes and obvious credentials."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'customizations/DeepTutor'


def check():
    manifest=json.loads((PACKAGE/'manifest.json').read_text(encoding='utf8'))
    assert manifest['version']=='v1.6.15'
    for name,expected in manifest['files'].items():
        target=(PACKAGE/'files'/name).resolve()
        assert target.is_relative_to((PACKAGE/'files').resolve()),name
        assert hashlib.sha256(target.read_bytes()).hexdigest()==expected,'Hash mismatch: '+name
    assert hashlib.sha256((PACKAGE/'tracked.patch').read_bytes()).hexdigest()==manifest['patch_sha256']
    assert 'manim==0.22.0' in (PACKAGE/'files/requirements-review-video.txt').read_text()
    assert (PACKAGE/'files/deeptutor/services/summary_notes/quick_review_v1/typography.json').is_file()
    tracked=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode('utf8').split('\0')
    problems=[]
    credentials=re.compile(rb'(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)')
    for rel in set(tracked):
        path=ROOT/rel
        if not rel or not path.is_file():continue
        if path.name.startswith('.env') and path.name!='.env.example':problems.append((rel,'environment configuration'))
        if path.suffix.lower() in {'.mp4','.m4a','.wav','.sqlite','.db','.dpapi'}:problems.append((rel,'personal media or runtime state'))
        if credentials.search(path.read_bytes()):problems.append((rel,'credential-like material'))
    assert not problems,'Publication scan failed (values withheld): '+repr(problems)
    print(f'Public package OK: {len(manifest["files"])} payload hashes, pinned patch and credential/media scan.')


if __name__=='__main__':check()
