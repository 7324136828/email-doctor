"""Stage 2 - sender normalization ("rebrand").

Rolls addresses like ``no-reply@mail.example.com`` and ``news@example.com`` up
into a single ``example.com`` sender group, applying an optional user-supplied
``aliases.json`` from the inputs directory.

aliases.json accepts either shape:
    {"example.com": ["mail.example.com", "news.example.com"]}
    {"mail.example.com": "example.com"}
"""
import json
from pathlib import Path

# Common second-level public suffixes where three labels are needed.
SECOND_LEVEL_TLDS = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk",
    "com.au", "net.au", "org.au", "co.nz",
    "co.jp", "or.jp", "co.kr", "co.in", "co.za",
    "com.br", "com.mx", "com.ar", "com.co", "com.cn",
    "com.hk", "com.sg", "com.tw", "com.tr",
}


def canonical_domain(domain: str) -> str:
    labels = domain.lower().strip(".").split(".")
    labels = [l for l in labels if l]
    if len(labels) <= 2:
        return ".".join(labels)
    suffix2 = ".".join(labels[-2:])
    if suffix2 in SECOND_LEVEL_TLDS and len(labels) >= 3:
        return ".".join(labels[-3:])
    return suffix2


def _load_aliases(inputs_dir: Path, log) -> dict[str, str]:
    alias_map: dict[str, str] = {}
    for path in sorted(inputs_dir.rglob("aliases.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            log(f"Ignoring invalid aliases file {path.name}: {exc}")
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if isinstance(value, list):
                for alias in value:
                    alias_map[str(alias).lower()] = key.lower()
            else:
                alias_map[key.lower()] = str(value).lower()
    return alias_map


def run(
    inputs_dir: Path,
    messages_path: Path,
    out_path: Path,
    aliases_out: Path,
    log=print,
) -> int:
    alias_map = _load_aliases(inputs_dir, log)
    observed: dict[str, str] = {}
    count = 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(messages_path, encoding="utf-8") as src, open(
        out_path, "w", encoding="utf-8"
    ) as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            domain = rec.get("from_domain") or ""
            canonical = canonical_domain(domain)
            group = alias_map.get(domain) or alias_map.get(canonical) or canonical
            rec["sender_domain"] = domain
            rec["sender_group"] = group or domain or "(unknown)"
            if domain:
                observed[domain] = group
            dst.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += 1

    aliases_out.parent.mkdir(parents=True, exist_ok=True)
    aliases_out.write_text(
        json.dumps(dict(sorted(observed.items())), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if alias_map:
        log(f"Applied {len(alias_map)} custom sender aliases")
    return count
