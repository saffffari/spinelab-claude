from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "src"
THEME_ROOT = SOURCE_ROOT / "spinelab" / "ui" / "theme"
SKIP_ROOTS = {
    THEME_ROOT,
    REPO_ROOT / "prototypes",
    REPO_ROOT / "docs",
    REPO_ROOT / "tests",
}
SOURCE_SUFFIXES = {".py"}
HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
QCOLOR_RE = re.compile(r"\bQColor\s*\(")
FONT_FAMILY_RE = re.compile(r"font-family")
WEIGHT_RE = re.compile(r"\b(?:font-weight|setWeight)\s*[:(]?\s*(\d{3})")
RADIUS_RE = re.compile(r"\b(?:border-radius|radius)\s*[:=]?\s*(\d+)")


def should_skip(path: Path) -> bool:
    return any(root in path.parents or path == root for root in SKIP_ROOTS)


def check_path(path: Path) -> list[str]:
    if path.suffix not in SOURCE_SUFFIXES or should_skip(path):
        return []
    issues: list[str] = []
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        if HEX_RE.search(line):
            issues.append(f"{path}:{lineno}: raw hex color outside theme files")
        if QCOLOR_RE.search(line):
            issues.append(f"{path}:{lineno}: direct QColor usage outside theme files")
        if FONT_FAMILY_RE.search(line):
            issues.append(f"{path}:{lineno}: font-family declaration outside theme files")
        weight_match = WEIGHT_RE.search(line)
        if weight_match and int(weight_match.group(1)) > 400:
            issues.append(f"{path}:{lineno}: font weight above regular")
        radius_match = RADIUS_RE.search(line)
        if radius_match and "concentric_radius" not in line and "capsule_radius" not in line:
            issues.append(f"{path}:{lineno}: radius literal outside geometry tokens")
    return issues


def main() -> int:
    issues: list[str] = []
    for path in SOURCE_ROOT.rglob("*"):
        if path.is_file():
            issues.extend(check_path(path))
    if issues:
        print("\n".join(issues))
        return 1
    print("Theme usage check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
