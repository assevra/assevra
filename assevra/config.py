"""
Project configuration: ``.assevra.yml``.

A tool people adopt is a tool whose invocation they do not have to remember. The
long CLI incantation — dataset, judge model, panel, thresholds, budgets, history
path, signing key — belongs in a file that lives next to the code, is reviewed in
pull requests, and makes every run on every machine identical. That file is
``.assevra.yml``:

    version: 1
    dataset: evals/agent.jsonl
    out_dir: .assevra/out

    judge:
      provider: anthropic
      model: claude-opus-4-8

    gate:
      enabled: true
      fail_on_regression: true

    thresholds:
      grounding: 0.92

Precedence is the boring, expected one: **built-in defaults < config file <
environment < explicit CLI flags.** Nothing in the config can silently override
something a human typed on the command line.

The parser is dependency-free on purpose. Assevra's core installs with no
third-party packages, and asking a team to add PyYAML before they can write a
config would undo that. PyYAML is used when it happens to be installed; otherwise
a small, strict parser handles the subset a configuration file needs — nested
mappings, block and inline lists, quoted and bare scalars, comments. Anything
outside that subset raises :class:`ConfigError` with a line number rather than
guessing.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

CONFIG_NAMES = (".assevra.yml", ".assevra.yaml", "assevra.yml", "assevra.yaml")

CONFIG_VERSION = 1


class ConfigError(Exception):
    """Raised for an unreadable or structurally invalid config file."""


# --------------------------------------------------------------------------- #
# Defaults                                                                     #
# --------------------------------------------------------------------------- #
# Every knob Assevra reads, with the value it takes when nobody says otherwise.
# This dict doubles as the documentation of the config surface: if a key is not
# here, `assevra validate --config` reports it as unknown rather than ignoring it
# silently (a typo'd threshold that is quietly dropped is worse than an error).
DEFAULTS: dict[str, Any] = {
    "version": CONFIG_VERSION,
    "dataset": "",
    "out_dir": ".",
    "judge": {
        "provider": "auto",
        "model": "",
        "panel": [],
        "base_url": "",
        "api_key_env": "",
        "max_tokens": 512,
        "temperature": 0.0,
    },
    "gate": {
        "enabled": False,
        "fail_on_regression": False,
    },
    "validate": {
        "strict": False,
        "on_run": True,
    },
    "thresholds": {},
    "budgets": {
        "cost_usd": None,
        "latency_ms": None,
        "price": {
            "input_per_mtok": None,
            "output_per_mtok": None,
        },
    },
    "reliability": {
        "pass_k": 2,
    },
    "history": {
        "path": "",
        "label": "",
        "baseline": "",
    },
    "signing": {
        "key": "",
        "public_key": "",
    },
    "attest": {
        "enabled": False,
    },
    "reports": {
        "formats": ["md", "json", "html"],
    },
    "calibration": {
        "label_field": "human_label",
        "kappa_bar": 0.85,
    },
}


# --------------------------------------------------------------------------- #
# A very small YAML subset parser (used when PyYAML is not installed)          #
# --------------------------------------------------------------------------- #
def _strip_comment(text: str) -> str:
    """Remove a trailing ``#`` comment that is not inside quotes."""
    out = []
    quote = None
    prev = ""
    for ch in text:
        if quote:
            out.append(ch)
            if ch == quote and prev != "\\":
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#" and (not out or out[-1] in " \t"):
            break
        else:
            out.append(ch)
        prev = ch
    return "".join(out).rstrip()


def _scalar(text: str, lineno: int) -> Any:
    """Parse one bare or quoted scalar."""
    text = text.strip()
    if not text:
        return None
    if text[0] in "\"'" and len(text) >= 2 and text[-1] == text[0]:
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part, lineno) for part in _split_inline(inner)]
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"line {lineno}: cannot parse inline mapping: {exc}") from exc
    low = text.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "none", "~"):
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _split_inline(inner: str) -> list[str]:
    """Split ``a, "b, c", d`` on top-level commas only."""
    parts, buf, quote, depth = [], [], None, 0
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _tokenize(text: str) -> list[tuple[int, int, str]]:
    """(lineno, indent, content) for every significant line."""
    lines = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ConfigError(f"line {lineno}: tabs are not valid indentation in YAML")
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        if stripped.strip() in ("---", "..."):
            continue
        indent = len(stripped) - len(stripped.lstrip())
        lines.append((lineno, indent, stripped.strip()))
    return lines


def _parse_block(lines: list[tuple[int, int, str]], i: int, indent: int) -> tuple[Any, int]:
    if i >= len(lines):
        return None, i
    if lines[i][2].startswith("- "):
        return _parse_seq(lines, i, indent)
    return _parse_map(lines, i, indent)


def _parse_seq(lines, i, indent) -> tuple[list, int]:
    items: list[Any] = []
    while i < len(lines):
        lineno, ind, content = lines[i]
        if ind < indent or not content.startswith("- "):
            break
        if ind > indent:
            raise ConfigError(f"line {lineno}: unexpected indentation in list")
        item = content[2:].strip()
        i += 1
        if not item:
            value, i = _parse_block(lines, i, ind + 2)
            items.append(value)
        elif ":" in item and not item.startswith(("\"", "'", "[", "{")):
            # A mapping that starts on the dash line: "- name: x".
            sub = [(lineno, ind + 2, item)]
            while i < len(lines) and lines[i][1] > ind:
                sub.append(lines[i])
                i += 1
            value, _ = _parse_map(sub, 0, ind + 2)
            items.append(value)
        else:
            items.append(_scalar(item, lineno))
    return items, i


def _parse_map(lines, i, indent) -> tuple[dict, int]:
    out: dict[str, Any] = {}
    while i < len(lines):
        lineno, ind, content = lines[i]
        if ind < indent:
            break
        if ind > indent:
            raise ConfigError(f"line {lineno}: unexpected indentation")
        if content.startswith("- "):
            break
        if ":" not in content:
            raise ConfigError(f"line {lineno}: expected 'key: value', got {content!r}")
        key, _, rest = content.partition(":")
        key = key.strip().strip("\"'")
        rest = rest.strip()
        i += 1
        if rest:
            out[key] = _scalar(rest, lineno)
            continue
        # Value is a nested block (or an empty value).
        if i < len(lines) and lines[i][1] > ind:
            value, i = _parse_block(lines, i, lines[i][1])
            out[key] = value
        elif i < len(lines) and lines[i][1] == ind and lines[i][2].startswith("- "):
            value, i = _parse_seq(lines, i, ind)
            out[key] = value
        else:
            out[key] = None
    return out, i


def parse_yaml(text: str) -> dict:
    """Parse a config document. Uses PyYAML when available, else the subset parser."""
    try:
        import yaml  # type: ignore
    except ImportError:
        pass
    else:
        loaded = yaml.safe_load(text)
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ConfigError("config must be a mapping at the top level")
        return loaded

    lines = _tokenize(text)
    if not lines:
        return {}
    value, _ = _parse_block(lines, 0, lines[0][1])
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError("config must be a mapping at the top level")
    return value


# --------------------------------------------------------------------------- #
# Loading + merging                                                            #
# --------------------------------------------------------------------------- #
def find_config(start: Optional[str] = None) -> Optional[Path]:
    """Walk up from `start` (default: cwd) looking for a config file."""
    here = Path(start or os.getcwd()).resolve()
    for directory in [here, *here.parents]:
        for name in CONFIG_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _unknown_keys(data: dict, defaults: dict, prefix: str = "") -> list[str]:
    """Config keys Assevra does not recognize — reported, never silently dropped."""
    unknown = []
    for key, value in data.items():
        path = f"{prefix}{key}"
        if key not in defaults:
            # `thresholds` is an open map of dimension -> float, as is
            # budgets.price; third-party scorers legitimately add keys there.
            if prefix.rstrip(".") in ("thresholds", "budgets.price"):
                continue
            unknown.append(path)
            continue
        if isinstance(value, dict) and isinstance(defaults.get(key), dict):
            unknown.extend(_unknown_keys(value, defaults[key], f"{path}."))
    return unknown


class Config:
    """A resolved configuration: defaults merged with the project file."""

    def __init__(self, data: dict, path: Optional[Path] = None, unknown: Optional[list] = None):
        self.data = data
        self.path = path
        self.unknown_keys = unknown or []

    # -- access ------------------------------------------------------------ #
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return default if node is None else node

    def pick(self, cli_value: Any, dotted: str, default: Any = None) -> Any:
        """CLI wins; then the config file; then the built-in default.

        `cli_value` counts as "given" only when it is neither None nor False —
        argparse store_true flags default to False, and a False flag must not
        override a config that turned the feature on.
        """
        if cli_value not in (None, False):
            return cli_value
        return self.get(dotted, default)

    def threshold(self, dimension: str) -> Optional[float]:
        value = self.get(f"thresholds.{dimension}")
        return None if value is None else float(value)

    def scorer_options(self) -> dict:
        """Options handed to every scorer (budgets, price table, thresholds)."""
        return {
            "budgets": self.get("budgets", {}) or {},
            "thresholds": self.get("thresholds", {}) or {},
        }

    def to_dict(self) -> dict:
        return json.loads(json.dumps(self.data))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        where = str(self.path) if self.path else "defaults only"
        return f"<Config {where}>"


def load(path: Optional[str] = None, start: Optional[str] = None) -> Config:
    """Load configuration, searching upward from `start` when `path` is omitted.

    Missing config is not an error: Assevra must work in a repo that has never
    heard of it. A config file that exists but cannot be parsed *is* an error —
    silently falling back to defaults would run the wrong evaluation.
    """
    found = Path(path) if path else find_config(start)
    if found is None:
        return Config(_deep_merge(DEFAULTS, {}), None, [])
    if not found.is_file():
        raise ConfigError(f"config not found: {found}")
    try:
        text = found.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"{found}: {exc}") from exc

    data = parse_yaml(text)
    version = data.get("version", CONFIG_VERSION)
    if version not in (None, CONFIG_VERSION):
        raise ConfigError(
            f"{found}: unsupported config version {version!r} "
            f"(this Assevra understands version {CONFIG_VERSION})"
        )
    unknown = _unknown_keys(data, DEFAULTS)
    return Config(_deep_merge(DEFAULTS, data), found, unknown)


TEMPLATE = """\
# Assevra — release evidence for AI agents.
# Docs: https://assevra.ai/docs/configuration
version: 1

# The labeled dataset to score. `assevra run` needs nothing else once this is set.
dataset: {dataset}
out_dir: {out_dir}

judge:
  # anthropic | openai | azure | bedrock | gemini | local | mock | none | auto
  provider: {provider}
  model: {model}
  # A panel of models votes as a jury; disagreement is reported as a signal.
  panel: []

gate:
  enabled: {gate}
  fail_on_regression: {fail_on_regression}

validate:
  # Refuse to score a dataset that has structurally invalid rows.
  on_run: true
  # Set true to also refuse rows that carry no answer key (recommended once
  # you have finished labeling — an unlabeled row scores as a vacuous pass).
  strict: false

# Per-dimension pass thresholds. Omit a dimension to keep the methodology default.
thresholds:
  grounding: 0.90
  safety: 1.00
  pii: 1.00
  task_completion: 0.90

# Budgets for the cost and latency dimensions (per row, unless a row overrides).
budgets:
  cost_usd: null
  latency_ms: null

reliability:
  # k for pass^k over repeated trials sharing a case_id.
  pass_k: 2

history:
  path: {history}

signing:
  # Ed25519 private key (PEM). Keep it out of git; point at a CI secret file.
  key: ''

attest:
  # Also emit an Agent Card mapping the evidence to governance frameworks.
  enabled: {attest}
"""


def render_template(
    dataset: str = "datasets/golden.jsonl",
    out_dir: str = ".assevra/out",
    provider: str = "auto",
    model: str = "",
    gate: bool = True,
    fail_on_regression: bool = True,
    history: str = ".assevra/history.jsonl",
    attest: bool = True,
) -> str:
    """Render a commented starter config (used by ``assevra init``)."""
    return TEMPLATE.format(
        dataset=dataset,
        out_dir=out_dir,
        provider=provider,
        model=model or "''",
        gate=str(bool(gate)).lower(),
        fail_on_regression=str(bool(fail_on_regression)).lower(),
        history=history,
        attest=str(bool(attest)).lower(),
    )
