from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Set
import sys


ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "Source"
RULESET_DIR = ROOT / "Ruleset"
PROVIDERS_DIR = ROOT / "Providers"

CST = timezone(timedelta(hours=8))


def log(message: str) -> None:
    print(message, flush=True)


def normalize_line(line: str) -> str:
    return line.strip()


def should_ignore(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith("#")


def read_source_rules(file_path: Path) -> List[str]:
    rules: List[str] = []
    with file_path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = normalize_line(raw)
            if should_ignore(line):
                continue
            rules.append(line)
    return rules


def deduplicate_rules(rules: List[str]) -> List[str]:
    seen = set()
    result = []
    for rule in rules:
        if rule not in seen:
            seen.add(rule)
            result.append(rule)
    return result


def sort_rules(rules: List[str]) -> List[str]:
    return sorted(rules)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def build_header(name: str, updated: str, total: int) -> str:
    return (
        f"# NAME: {name}\n"
        f"# UPDATED: {updated}\n"
        f"# TOTAL: {total}\n"
    )


def build_list_content(name: str, updated: str, rules: List[str]) -> str:
    header = build_header(name, updated, len(rules))
    body = "\n".join(rules)
    return header + "\n" + body + ("\n" if body else "")


def build_yaml_content(name: str, updated: str, rules: List[str]) -> str:
    header = build_header(name, updated, len(rules))
    payload_lines = ["payload:"]
    payload_lines.extend([f"  - {rule}" for rule in rules])
    return header + "\n" + "\n".join(payload_lines) + "\n"


def extract_effective_body(content: str) -> str:
    lines = content.splitlines()
    if len(lines) >= 4 and lines[0].startswith("# NAME:") and lines[1].startswith("# UPDATED:") and lines[2].startswith("# TOTAL:"):
        return "\n".join(lines[3:]).lstrip("\n")
    return content


def write_if_effective_content_changed(path: Path, content: str) -> bool:
    ensure_parent(path)

    if path.exists():
        old_content = path.read_text(encoding="utf-8")
        if extract_effective_body(old_content) == extract_effective_body(content):
            return False

    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def delete_stale_files(base_dir: Path, expected_files: Set[Path], suffix: str) -> int:
    deleted = 0
    if not base_dir.exists():
        return 0

    for file in base_dir.rglob(f"*{suffix}"):
        if file not in expected_files:
            file.unlink()
            deleted += 1
            log(f"[DELETE] stale file removed: {file.relative_to(ROOT)}")

    # 尝试删除空目录
    for d in sorted([p for p in base_dir.rglob("*") if p.is_dir()], reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass

    return deleted


def main() -> int:
    log("========================================")
    log("Rules Build Started")
    log("========================================")

    if not SOURCE_DIR.exists():
        log(f"[ERROR] Source directory not found: {SOURCE_DIR}")
        return 1

    RULESET_DIR.mkdir(parents=True, exist_ok=True)
    PROVIDERS_DIR.mkdir(parents=True, exist_ok=True)

    source_files = sorted(SOURCE_DIR.rglob("*.list"))

    if not source_files:
        log("[WARN] No .list files found under Source/")
        return 0

    log(f"[INFO] Found {len(source_files)} source file(s)")

    updated = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")

    total_files = 0
    updated_list_files = 0
    updated_yaml_files = 0

    expected_ruleset_files: Set[Path] = set()
    expected_provider_files: Set[Path] = set()

    for src_file in source_files:
        total_files += 1
        relative = src_file.relative_to(SOURCE_DIR)
        name = src_file.stem

        raw_rules = read_source_rules(src_file)
        raw_count = len(raw_rules)

        deduped_rules = deduplicate_rules(raw_rules)
        deduped_count = len(deduped_rules)

        sorted_rules = sort_rules(deduped_rules)
        final_count = len(sorted_rules)

        ruleset_output = RULESET_DIR / relative
        provider_output = (PROVIDERS_DIR / relative).with_suffix(".yaml")

        expected_ruleset_files.add(ruleset_output)
        expected_provider_files.add(provider_output)

        list_content = build_list_content(name, updated, sorted_rules)
        yaml_content = build_yaml_content(name, updated, sorted_rules)

        list_written = write_if_effective_content_changed(ruleset_output, list_content)
        yaml_written = write_if_effective_content_changed(provider_output, yaml_content)

        if list_written:
            updated_list_files += 1
        if yaml_written:
            updated_yaml_files += 1

        log(
            f"[BUILD] {src_file.relative_to(ROOT)} | "
            f"raw={raw_count}, dedup={deduped_count}, final={final_count} | "
            f"list={'updated' if list_written else 'unchanged'} | "
            f"yaml={'updated' if yaml_written else 'unchanged'}"
        )

    deleted_list_files = delete_stale_files(RULESET_DIR, expected_ruleset_files, ".list")
    deleted_yaml_files = delete_stale_files(PROVIDERS_DIR, expected_provider_files, ".yaml")

    log("========================================")
    log("Rules Build Finished")
    log("========================================")
    log(f"[SUMMARY] total source files : {total_files}")
    log(f"[SUMMARY] updated list files : {updated_list_files}")
    log(f"[SUMMARY] updated yaml files : {updated_yaml_files}")
    log(f"[SUMMARY] deleted list files : {deleted_list_files}")
    log(f"[SUMMARY] deleted yaml files : {deleted_yaml_files}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
