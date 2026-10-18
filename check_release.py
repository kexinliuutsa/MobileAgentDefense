#!/usr/bin/env python3
"""Pre-publication scan. Fail closed on common identifiers, secrets, or datasets.

No scanner can guarantee anonymity. Also inspect commit history and binaries manually.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TEXT_EXT = {'.py','.c','.h','.md','.txt','.sh','.toml','.yml','.yaml','.json','.ini','.gitignore','.gitattributes'}
BAD_SUFFIXES = {'.db','.sqlite','.sqlite3','.dta','.csv','.png','.jpg','.jpeg','.pdf','.mp4','.mov','.pt','.pth','.pkl','.pickle','.joblib','.onnx','.bin','.key','.pem','.env','.zip','.tar','.gz'}
BAD_DIRS = {'.git','runs','real_device_online','data','secrets','screenshots','__pycache__','build','.venv','venv','node_modules'}
RULES = [
    ('absolute-user-directory',re.compile(r'(?:/Users/[A-Za-z0-9_.-]+/|/home/[A-Za-z0-9_.-]+/|[A-Za-z]:\\\\Users\\\\)',re.I)),
    ('secret-token',re.compile(r'(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{18,}|github_pat_[A-Za-z0-9_]{18,}|AIza[A-Za-z0-9_-]{25,})')),
    ('private-key',re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
    ('possible-email',re.compile(r'(?<![\w.-])[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}')),
]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--term',action='append',default=[],help='Extra identity term to forbid; may repeat')
    ns=ap.parse_args()
    errors=[]
    for p in ROOT.rglob('*'):
        if not p.is_file(): continue
        rel=p.relative_to(ROOT)
        if any(part in BAD_DIRS for part in rel.parts[:-1]): continue
        if p.suffix.lower() in BAD_SUFFIXES:
            errors.append((str(rel),'restricted artifact type'))
            continue
        if p.suffix.lower() not in TEXT_EXT and p.name not in ('.gitignore','Makefile'):
            errors.append((str(rel),'unexpected file type'))
            continue
        raw=p.read_bytes()
        if b'\0' in raw:
            errors.append((str(rel),'binary file')); continue
        txt=raw.decode('utf-8',errors='replace')
        for name,pattern in RULES:
            if name == 'possible-email':
                emails = [m.group(0) for m in pattern.finditer(txt)]
                if any(e != 'anonymous@example.invalid' for e in emails):
                    errors.append((str(rel),name))
            elif pattern.search(txt):
                errors.append((str(rel),name))
        for term in ns.term:
            if term and term.lower() in txt.lower():errors.append((str(rel),'private term passed via --term'))
    if errors:
        print('RELEASE CHECK FAIL (fix and inspect before publishing):')
        for path,reason in sorted(set(errors)):print(' -',path,reason)
        return 2
    print('RELEASE CHECK PASS (heuristic only; manual review still required)')
    print('IMPORTANT: scan git history, screenshots, source provenance, API logs, dependencies, licenses.')
    return 0

if __name__=='__main__':sys.exit(main())
