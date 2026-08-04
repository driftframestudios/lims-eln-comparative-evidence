from __future__ import annotations

import re
from pathlib import Path
import sys


PATTERNS = (
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,255}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,255}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b", re.IGNORECASE),
    re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s/]+@", re.IGNORECASE),
)


def scan(root: Path) -> list[str]:
    findings: list[str] = []
    if not root.is_dir():
        return [f"{root}: generated-artifact directory requires a completed generation step"]
    files = sorted(item for item in root.rglob("*") if item.is_file())
    if not files:
        return [f"{root}: generated-artifact directory requires at least one file"]
    for path in files:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(f"{path}: binary artifact requires governed inspection")
            continue
        for pattern in PATTERNS:
            if pattern.search(content):
                findings.append(f"{path}: credential-shaped content requires governed storage")
                break
    return findings


def main() -> int:
    roots = [Path(argument) for argument in sys.argv[1:]]
    if not roots:
        print("artifact checker requires at least one generated-artifact directory")
        return 2
    findings = [finding for root in roots for finding in scan(root)]
    if findings:
        print("\n".join(findings))
        return 1
    print("artifact secret-shape gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
