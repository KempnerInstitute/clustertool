"""Command discovery and ranking for 'clustertools search'."""

import difflib
import math
import re

import click

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    """Return the lowercase word tokens in a string."""
    return _WORD.findall(text.lower())


def collect_commands(root: click.Group, ctx: click.Context) -> list[dict]:
    """Return a searchable record for every leaf command under root."""
    records: list[dict] = []

    def walk(group: click.Group, prefix: str) -> None:
        for name in group.list_commands(ctx):
            command = group.get_command(ctx, name)
            if command is None or command.hidden:
                continue
            path = f"{prefix}{name}".strip()
            if isinstance(command, click.Group):
                walk(command, f"{path} ")
            else:
                records.append(_record(path, command))

    walk(root, "")
    return records


def _record(path: str, command: click.Command) -> dict:
    """Build a searchable record from a command's path, help, and keywords."""
    short = command.get_short_help_str(120)
    full = command.help or ""
    kw = getattr(command, "search_keywords", ())
    name_tokens = set(_tokens(path))
    kw_tokens = {token for term in kw for token in _tokens(term)}
    short_tokens = set(_tokens(short))
    full_tokens = set(_tokens(full))
    return {
        "path": path,
        "name": path.split()[-1],
        "short": short,
        "scope": getattr(command, "scope", "user"),
        "name_tokens": name_tokens,
        "kw_tokens": kw_tokens,
        "short_tokens": short_tokens,
        "full_tokens": full_tokens,
        "all_tokens": name_tokens | kw_tokens | short_tokens | full_tokens,
    }


def _token_score(record: dict, token: str) -> float:
    """Score how strongly one query token matches a command record."""
    if token == record["name"]:
        return 10.0
    if token in record["name_tokens"] or token in record["kw_tokens"]:
        return 7.0
    names = record["name_tokens"] | record["kw_tokens"]
    if len(token) >= 3 and any(token in word for word in names):
        return 5.0
    if token in record["short_tokens"]:
        return 4.0
    if token in record["full_tokens"]:
        return 2.0
    pool = record["name_tokens"] | record["kw_tokens"] | record["short_tokens"]
    best = max((difflib.SequenceMatcher(None, token, word).ratio() for word in pool), default=0.0)
    return 3.0 * best if best >= 0.82 else 0.0


def rank(records: list[dict], query: list[str], limit: int = 10) -> list[dict]:
    """Return the best-matching command records for the query, most relevant first.

    Each query token is scored per command by where it matches (name and
    keywords rank above the short help, which ranks above the full help), with a
    fuzzy fallback for typos. Rarer terms weigh more (inverse document
    frequency), and matching more of the query terms adds a coverage bonus.
    """
    tokens = _tokens(" ".join(query))
    if not tokens or not records:
        return []
    total = len(records)
    idf = {}
    for token in set(tokens):
        freq = sum(1 for record in records if token in record["all_tokens"])
        idf[token] = math.log((total + 1) / (freq + 1)) + 1.0
    scored: list[tuple[float, dict]] = []
    for record in records:
        score = 0.0
        matched = 0
        for token in tokens:
            value = _token_score(record, token)
            if value > 0:
                matched += 1
                score += value * idf[token]
        if not matched:
            continue
        score *= 0.5 + 0.5 * (matched / len(tokens))
        scored.append((score, record))
    if not scored:
        return []
    scored.sort(key=lambda item: (-item[0], item[1]["path"]))
    best = scored[0][0]
    return [record for score, record in scored if score >= 0.2 * best][:limit]


def suggest(records: list[dict], query: list[str], limit: int = 3) -> list[str]:
    """Return command paths whose names are closest to the query, for no-match hints."""
    by_name = {record["name"]: record["path"] for record in records}
    joined = " ".join(query).lower()
    close = difflib.get_close_matches(joined, list(by_name), n=limit, cutoff=0.5)
    return [by_name[name] for name in close]
