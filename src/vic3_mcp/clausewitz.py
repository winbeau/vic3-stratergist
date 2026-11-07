"""Parse rakaly-melted Victoria 3 (Clausewitz / Jomini) text."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

Scalar = str | int | float | bool | None
Node = Scalar | dict[str, Any] | list[Any]


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, text: str):
        self.s = text
        self.n = len(text)
        self.i = 0

    def peek(self) -> str:
        return self.s[self.i] if self.i < self.n else ""

    def skip_ws(self) -> None:
        s, n, i = self.s, self.n, self.i
        while i < n and s[i] in " \t\r\n":
            i += 1
        self.i = i

    def parse_value(self) -> Node:
        self.skip_ws()
        c = self.peek()
        if c == "{":
            return self.parse_brace()
        if c == '"':
            return self.parse_quoted()
        if c == "":
            raise ParseError("unexpected end of input")
        return self.parse_atom()

    def parse_brace(self) -> Node:
        self.i += 1  # {
        self.skip_ws()
        if self.peek() == "}":
            self.i += 1
            return {}
        pairs: dict[str, Any] = {}
        values: list[Any] = []
        saw_pair = False
        while True:
            self.skip_ws()
            if self.peek() == "}":
                self.i += 1
                break
            if self.peek() == "":
                break
            if self._looks_like_dict():
                key = self.parse_key()
                self.skip_ws()
                if self.peek() != "=":
                    values.append(_coerce_number(key) if key else key)
                    continue
                self.i += 1
                _assign(pairs, key, self.parse_value())
                saw_pair = True
            else:
                values.append(self.parse_value())
        if saw_pair and not values:
            return pairs
        if saw_pair and values:
            # Sparse array: leading count then key=value entries.
            numeric_vals = [v for v in values if isinstance(v, (int, float))]
            if numeric_vals and len(numeric_vals) == len(values):
                return pairs
            pairs["_values"] = values
            return pairs
        return values

    def _looks_like_dict(self) -> bool:
        j = self.i
        s, n = self.s, self.n
        while j < n and s[j] in " \t\r\n":
            j += 1
        if j >= n or s[j] == "}":
            return True
        if s[j] == '"':
            j += 1
            while j < n and s[j] != '"':
                if s[j] == "\\":
                    j += 2
                    continue
                j += 1
            j += 1
            while j < n and s[j] in " \t":
                j += 1
            return j < n and s[j] == "="
        if s[j] == "{":
            return False
        # ident or number then =
        while j < n and s[j] not in " \t\r\n{}=":
            j += 1
        while j < n and s[j] in " \t":
            j += 1
        return j < n and s[j] == "="

    def parse_pairs(self, consume_close: bool) -> dict[str, Any]:
        out: dict[str, Any] = {}
        while True:
            self.skip_ws()
            if self.i >= self.n:
                break
            if consume_close and self.peek() == "}":
                self.i += 1
                break
            if self.peek() == "{":
                # anonymous object inside a map
                _assign(out, "_items", self.parse_value())
                continue
            key = self.parse_key()
            if key == "":
                break
            self.skip_ws()
            if self.peek() != "=":
                _assign(out, key, True)
                continue
            self.i += 1
            _assign(out, key, self.parse_value())
        return out

    def parse_key(self) -> str:
        self.skip_ws()
        if self.peek() == '"':
            return self.parse_quoted()
        start = self.i
        s, n = self.s, self.n
        while self.i < n and s[self.i] not in " \t\r\n{}=":
            self.i += 1
        return s[start : self.i]

    def parse_quoted(self) -> str:
        self.i += 1
        s, n = self.s, self.n
        chunks: list[str] = []
        start = self.i
        while self.i < n:
            c = s[self.i]
            if c == '"':
                chunks.append(s[start : self.i])
                self.i += 1
                return "".join(chunks)
            if c == "\\" and self.i + 1 < n:
                chunks.append(s[start : self.i])
                nxt = s[self.i + 1]
                chunks.append({"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(nxt, nxt))
                self.i += 2
                start = self.i
                continue
            self.i += 1
        chunks.append(s[start : self.i])
        return "".join(chunks)

    def parse_atom(self) -> Scalar:
        start = self.i
        s, n = self.s, self.n
        while self.i < n and s[self.i] not in " \t\r\n{}=":
            self.i += 1
        tok = s[start : self.i]
        if tok == "yes":
            return True
        if tok == "no":
            return False
        if tok in ("none", ""):
            return None
        if tok == "rgb":
            self.skip_ws()
            if self.peek() == "{":
                return {"rgb": self.parse_value()}
            return tok
        return _coerce_number(tok)


def _coerce_number(tok: str) -> Scalar:
    if tok.startswith("0x") or tok.startswith("0X"):
        try:
            return int(tok, 16)
        except ValueError:
            return tok
    if "." in tok:
        parts = tok.split(".")
        if len(parts) >= 3 and all(p.lstrip("-").isdigit() and p.lstrip("-") != "" for p in parts):
            return tok
        try:
            return float(tok)
        except ValueError:
            return tok
    try:
        return int(tok)
    except ValueError:
        return tok


def _assign(d: dict[str, Any], key: str, value: Any) -> None:
    if key in d:
        old = d[key]
        if isinstance(old, list):
            old.append(value)
        else:
            d[key] = [old, value]
    else:
        d[key] = value


def parse_text(text: str) -> Node:
    """Parse a melted Clausewitz snippet into dict/list/scalars."""
    p = Parser(text)
    p.skip_ws()
    if p.i >= p.n:
        return {}
    if p._looks_like_dict():
        return p.parse_pairs(consume_close=False)
    return p.parse_value()


def strip_sav_header(text: str) -> str:
    if text.startswith("SAV"):
        nl = text.find("\n")
        if nl != -1:
            return text[nl + 1 :]
    return text


def index_top_level(path: Path) -> dict[str, tuple[int, int]]:
    """Map top-level key -> (start_line, end_line) inclusive, 1-based."""
    keys: dict[str, tuple[int, int]] = {}
    current: str | None = None
    start = 0
    depth = 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            if lineno == 1 and line.startswith("SAV"):
                continue
            stripped = line.strip()
            if depth == 0 and "=" in stripped:
                key = stripped.split("=", 1)[0]
                current = key
                start = lineno
            depth += line.count("{") - line.count("}")
            if current is not None and depth <= 0:
                keys[current] = (start, lineno)
                current = None
                depth = 0
    return keys


def read_lines(path: Path, start: int, end: int) -> list[str]:
    lines: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            if lineno < start:
                continue
            if lineno > end:
                break
            lines.append(line)
    return lines


def read_section(path: Path, start: int, end: int) -> str:
    return "".join(read_lines(path, start, end))


def iter_database_entries(
    path: Path,
    manager_start: int,
    manager_end: int,
    skip_keys: frozenset[str] | None = None,
) -> Iterator[tuple[int, str]]:
    """Yield (numeric_id, entry_text) for `id={` records inside a manager.database."""
    skip_keys = skip_keys or frozenset()
    depth = 0
    capturing = False
    cap_depth = 0
    buf: list[str] = []
    entry_id: int | None = None
    skipping = False
    skip_depth = 0

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            if lineno < manager_start:
                continue
            if lineno > manager_end:
                break
            stripped = line.strip()
            if not capturing:
                depth += line.count("{") - line.count("}")
                if (
                    stripped.endswith("={")
                    and stripped[:-2].isdigit()
                    and depth >= 2
                ):
                    capturing = True
                    entry_id = int(stripped[:-2])
                    buf = [line]
                    cap_depth = line.count("{") - line.count("}")
                    skipping = False
                continue

            if skipping:
                skip_depth += line.count("{") - line.count("}")
                if skip_depth <= 0:
                    skipping = False
                cap_depth += line.count("{") - line.count("}")
                if cap_depth <= 0:
                    yield entry_id or 0, "".join(buf)
                    capturing = False
                    buf = []
                    depth = 2
                continue

            if skip_keys and cap_depth == 1:
                key = stripped.split("=", 1)[0] if "=" in stripped else ""
                if key in skip_keys and stripped.endswith("={"):
                    skipping = True
                    skip_depth = line.count("{") - line.count("}")
                    cap_depth += skip_depth
                    buf.append(f"{key}={{}}\n")
                    continue

            buf.append(line)
            cap_depth += line.count("{") - line.count("}")
            if cap_depth <= 0:
                yield entry_id or 0, "".join(buf)
                capturing = False
                buf = []
                depth = 2


def first_scalar(obj: Any, *path: str, default: Any = None) -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def last_channel_value(trend: Any) -> float | None:
    """Read the latest sample from a Vic3 trend {sample_rate, channels={0={values=...}}}."""
    if not isinstance(trend, dict):
        return None
    channels = trend.get("channels")
    if not isinstance(channels, dict):
        return None
    ch0 = channels.get(0) or channels.get("0")
    if not isinstance(ch0, dict):
        # channels may be a single dict already
        values = channels.get("values")
        if isinstance(values, list) and values:
            return float(values[-1])
        return None
    values = ch0.get("values")
    if isinstance(values, list) and values:
        try:
            return float(values[-1])
        except (TypeError, ValueError):
            return None
    if isinstance(values, (int, float)):
        return float(values)
    return None


def parse_sparse_array(value: Any) -> dict[int, float]:
    """Parse `15 1=179 2=622` style lists/dicts into {index: number}."""
    out: dict[int, float] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            try:
                out[int(k)] = float(v) if not isinstance(v, dict) else float(
                    v.get("total", 0) if isinstance(v, dict) else 0
                )
            except (TypeError, ValueError):
                continue
        return out
    if isinstance(value, list):
        # mixed: first int may be count, then we won't see key=value
        return out
    if isinstance(value, str):
        for part in value.split():
            if "=" in part:
                k, v = part.split("=", 1)
                try:
                    out[int(k)] = float(v)
                except ValueError:
                    continue
    return out
