"""Atlassian Document Format (ADF) <-> Markdown conversion."""

import copy
import re
import uuid

from markdown_it import MarkdownIt
from markdown_it.token import Token


def adf_to_text(adf: dict | None) -> str:
    """Convert ADF JSON to plain text."""
    if not adf or not isinstance(adf, dict):
        return ""
    return _convert_nodes(adf.get("content", []))


def _convert_nodes(nodes: list) -> str:
    parts = []
    for node in nodes:
        node_type = node.get("type", "")
        content = node.get("content", [])

        if node_type == "paragraph":
            parts.append(_convert_inline(content))

        elif node_type == "heading":
            level = node.get("attrs", {}).get("level", 1)
            parts.append(f"{'#' * level} {_convert_inline(content)}")

        elif node_type == "bulletList":
            for item in content:
                item_text = _convert_nodes(item.get("content", []))
                parts.append(f"- {item_text}")

        elif node_type == "taskList":
            for item in content:
                if item.get("type") != "taskItem":
                    continue
                state = (item.get("attrs") or {}).get("state", "TODO")
                marker = "[x]" if state == "DONE" else "[ ]"
                item_text = _convert_inline(item.get("content", []))
                parts.append(f"- {marker} {item_text}".rstrip())

        elif node_type == "orderedList":
            for i, item in enumerate(content, 1):
                item_text = _convert_nodes(item.get("content", []))
                parts.append(f"{i}. {item_text}")

        elif node_type == "codeBlock":
            lang = node.get("attrs", {}).get("language", "")
            code = _convert_inline(content)
            parts.append(f"```{lang}\n{code}\n```")

        elif node_type == "blockquote":
            text = _convert_nodes(content)
            parts.append("\n".join(f"> {line}" for line in text.split("\n")))

        elif node_type == "table":
            parts.append(_convert_table(content))

        elif node_type == "mediaGroup" or node_type == "mediaSingle":
            for media in content:
                if media.get("type") == "media":
                    media_id = media.get("attrs", {}).get("id", "unknown")
                    parts.append(f"[image: {media_id}]")

        elif node_type == "rule":
            parts.append("---")

        elif node_type == "panel":
            panel_type = node.get("attrs", {}).get("panelType", "info")
            text = _convert_nodes(content)
            parts.append(f"[{panel_type}] {text}")

        elif node_type == "listItem":
            parts.append(_convert_nodes(content))

        else:
            if content:
                parts.append(_convert_nodes(content))

    return "\n".join(parts)


def _convert_inline(nodes: list) -> str:
    parts = []
    for node in nodes:
        node_type = node.get("type", "")
        if node_type == "text":
            parts.append(_wrap_marks(node.get("text", ""), node.get("marks") or []))
        elif node_type == "mention":
            attrs = node.get("attrs", {})
            name = (attrs.get("text") or "").lstrip("@") or "unknown"
            mention_id = attrs.get("id")
            if mention_id:
                parts.append(f"@[{mention_id}:{name}]")
            else:
                parts.append(f"@{name}")
        elif node_type == "emoji":
            parts.append(node.get("attrs", {}).get("shortName", ""))
        elif node_type == "hardBreak":
            parts.append("\n")
        elif node_type == "inlineCard":
            parts.append(node.get("attrs", {}).get("url", ""))
        else:
            text = node.get("text", "")
            if text:
                parts.append(text)
    return "".join(parts)


def _mark_affixes(marks: list) -> tuple[str, str]:
    """Return the (prefix, suffix) Markdown syntax for a set of ADF marks.

    Wrapping order is innermost → outermost so that a re-parse produces the
    same mark set. `code` is innermost because Markdown code spans don't
    re-parse their contents; `link` is outermost because the link text can
    carry other formatting.
    """
    by_type = {m.get("type"): m for m in marks if isinstance(m, dict)}
    prefix = ""
    suffix = ""
    if "code" in by_type:
        prefix, suffix = "`" + prefix, suffix + "`"
    if "strike" in by_type:
        prefix, suffix = "~~" + prefix, suffix + "~~"
    if "em" in by_type:
        prefix, suffix = "*" + prefix, suffix + "*"
    if "strong" in by_type:
        prefix, suffix = "**" + prefix, suffix + "**"
    if "link" in by_type:
        href = (by_type["link"].get("attrs") or {}).get("href", "")
        if href:
            prefix, suffix = "[" + prefix, suffix + f"]({href})"
    return prefix, suffix


def _wrap_marks(text: str, marks: list) -> str:
    """Re-emit ADF inline marks as Markdown syntax."""
    if not text or not marks:
        return text
    prefix, suffix = _mark_affixes(marks)
    return f"{prefix}{text}{suffix}"


def _convert_table(rows: list) -> str:
    """Emit an ADF table as a GFM table so it survives a Markdown round-trip.

    GFM requires a delimiter row (`| --- |`) after the first row; without it,
    a re-parse turns the table into a paragraph of literal pipes. Cell text is
    flattened to one line and its pipes escaped for the same reason.
    """
    if not rows:
        return ""
    text_rows: list[list[str]] = []
    for row in rows:
        cells = []
        for cell in row.get("content", []):
            text = _convert_nodes(cell.get("content", []))
            cells.append(" ".join(text.split()).replace("|", "\\|"))
        text_rows.append(cells)
    width = max(len(cells) for cells in text_rows)
    lines = []
    for i, cells in enumerate(text_rows):
        cells = cells + [""] * (width - len(cells))
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("|" + " --- |" * width)
    return "\n".join(lines)


class PatchConflict(ValueError):
    """Two matches widened into the same formatting run, so neither can be applied."""


# Blocks whose inline content `adf_to_text` renders as Markdown. A patch that
# lands in one of these is matched against — and re-parsed as — Markdown.
# `codeBlock` is deliberately excluded: its text is literal.
_MARKDOWN_INLINE_BLOCKS = {"paragraph", "heading", "taskItem", "decisionItem"}


def patch_adf_markdown(adf: dict, old_string: str, new_string: str) -> tuple[dict, int]:
    """Replace a Markdown snippet inside an ADF document, preserving the rest.

    Returns (patched copy, occurrence count); the input document is not
    modified. Matching happens against the same Markdown `adf_to_text` emits,
    so `old_string` may carry formatting syntax (`**bold**`, `[text](url)`,
    `` `code` ``, `@[id:Name]`) and may straddle a mark boundary. The change
    range is then widened to the enclosing text runs, those runs are dropped,
    and `new_string` is converted Markdown → ADF in their place. Everything
    outside that range — other blocks, tables, panels, media, node types this
    module doesn't understand — is copied through untouched.

    A match that stays inside a single formatted run inherits that run's marks,
    so replacing a word inside bold text keeps it bold. A match that spans runs
    takes its formatting from `new_string` alone.

    Raises PatchConflict when two matches widen into the same run.
    """
    doc = copy.deepcopy(adf)
    count = 0

    def walk(node: dict) -> None:
        nonlocal count
        node_type = node.get("type")
        children = node.get("content")
        if not isinstance(children, list):
            return
        if node_type == "codeBlock":
            # Code is literal: Markdown syntax inside it means nothing.
            count += _patch_literal_children(node, old_string, new_string)
            return
        if node_type in _MARKDOWN_INLINE_BLOCKS:
            count += _patch_inline_block(node, old_string, new_string)
            return
        for child in children:
            if not isinstance(child, dict):
                continue
            if child.get("type") == "text":
                # Bare text under a block we don't model — patch it verbatim.
                count += _patch_literal_children(node, old_string, new_string)
                return
            walk(child)

    walk(doc)
    return doc, count


def _patch_literal_children(node: dict, old_string: str, new_string: str) -> int:
    """Replace old_string in a node's direct text children, without Markdown.

    A replacement that empties a text node removes the node (ADF forbids
    empty text), and a container emptied that way drops its `content` key
    rather than keeping an empty list.
    """
    children = node.get("content")
    if not isinstance(children, list):
        return 0
    count = 0
    for child in children:
        if not isinstance(child, dict) or child.get("type") != "text":
            continue
        text = child.get("text")
        if isinstance(text, str) and old_string in text:
            count += text.count(old_string)
            child["text"] = text.replace(old_string, new_string)
    if count:
        _set_content(node, [
            c for c in children
            if not (isinstance(c, dict) and c.get("type") == "text" and c.get("text") == "")
        ])
    return count


def _patch_inline_block(node: dict, old_string: str, new_string: str) -> int:
    """Patch one Markdown-rendered block; returns the number of replacements."""
    children = node.get("content")
    if not isinstance(children, list) or not children:
        return 0
    rendered, spans = _render_inline_with_spans(children)
    hits = _find_all(rendered, old_string)
    if not hits:
        return 0

    pieces: list[dict] = []
    cursor = 0
    for start in hits:
        end = start + len(old_string)
        lo = _snap_left(spans, start)
        hi = _snap_right(spans, end)
        if lo < cursor:
            raise PatchConflict(old_string)
        pieces.extend(_clip_nodes(spans, cursor, lo))
        replacement = markdown_inline_to_adf(new_string)
        _apply_marks(replacement, _run_marks(spans, start, end))
        pieces.extend(replacement)
        cursor = hi
    pieces.extend(_clip_nodes(spans, cursor, len(rendered)))
    _set_content(node, _merge_text_nodes(pieces))
    return len(hits)


def _set_content(node: dict, content: list[dict]) -> None:
    if content:
        node["content"] = content
    else:
        node.pop("content", None)


def _find_all(haystack: str, needle: str) -> list[int]:
    """Offsets of every non-overlapping occurrence, left to right."""
    out: list[int] = []
    start = 0
    while True:
        i = haystack.find(needle, start)
        if i < 0:
            return out
        out.append(i)
        start = i + len(needle)


def _render_inline_with_spans(nodes: list) -> tuple[str, list[dict]]:
    """Render inline nodes to Markdown, mapping each node to its offsets.

    Each span is `{start, end, text_start, text_end, node}`. For a text node,
    `[text_start, text_end)` is the slice of the rendered string that maps 1:1
    onto `node["text"]`, with the mark syntax lying outside it. Other nodes
    (mentions, emoji, hard breaks, inline cards) have `text_start is None` and
    are atomic: a patch can consume them whole but never split them.
    """
    parts: list[str] = []
    spans: list[dict] = []
    pos = 0
    for node in nodes:
        text = node.get("text")
        if node.get("type") == "text" and isinstance(text, str):
            prefix, suffix = _mark_affixes(node.get("marks") or []) if text else ("", "")
            rendered = f"{prefix}{text}{suffix}"
            spans.append({
                "start": pos,
                "end": pos + len(rendered),
                "text_start": pos + len(prefix),
                "text_end": pos + len(prefix) + len(text),
                "node": node,
            })
        else:
            rendered = _convert_inline([node])
            spans.append({
                "start": pos,
                "end": pos + len(rendered),
                "text_start": None,
                "text_end": None,
                "node": node,
            })
        parts.append(rendered)
        pos += len(rendered)
    return "".join(parts), spans


def _snap_left(spans: list[dict], pos: int) -> int:
    """Widen a match start left until it sits on a boundary we can cut at.

    Cutting inside a run's own text is safe (the tail keeps its marks); cutting
    inside mark syntax or an atomic node is not, so the whole node is consumed.
    """
    for span in spans:
        if span["start"] < pos < span["end"]:
            if span["text_start"] is not None and span["text_start"] <= pos <= span["text_end"]:
                return pos
            return span["start"]
    return pos


def _snap_right(spans: list[dict], pos: int) -> int:
    """Widen a match end right to the mirror image of `_snap_left`."""
    for span in spans:
        if span["start"] < pos < span["end"]:
            if span["text_start"] is not None and span["text_start"] <= pos <= span["text_end"]:
                return pos
            return span["end"]
    return pos


def _clip_nodes(spans: list[dict], lo: int, hi: int) -> list[dict]:
    """Rebuild the inline nodes covering rendered range [lo, hi)."""
    out: list[dict] = []
    for span in spans:
        if span["start"] == span["end"]:
            # A node that renders to nothing has no offsets to overlap, so it
            # would fall out of every clip. Keep it unless the edit swallowed
            # it, and let the inclusive bounds hand it to exactly one clip.
            if lo <= span["start"] <= hi:
                out.append(copy.deepcopy(span["node"]))
            continue
        if span["end"] <= lo or span["start"] >= hi:
            continue
        if lo <= span["start"] and span["end"] <= hi:
            out.append(copy.deepcopy(span["node"]))
            continue
        # Partial overlap is only reachable on a text node, because both
        # bounds were snapped to a text slice or a node edge.
        text_start = span["text_start"]
        if text_start is None:
            continue
        node = span["node"]
        head = max(lo, text_start) - text_start
        tail = min(hi, span["text_end"]) - text_start
        text = node["text"][head:tail]
        if not text:
            continue
        clipped: dict = {"type": "text", "text": text}
        if node.get("marks"):
            clipped["marks"] = copy.deepcopy(node["marks"])
        out.append(clipped)
    return out


def _run_marks(spans: list[dict], lo: int, hi: int) -> list[dict]:
    """Marks of the single formatted run a match sits inside, if there is one."""
    for span in spans:
        text_start = span["text_start"]
        if text_start is None:
            continue
        if text_start <= lo and hi <= span["text_end"] and span["node"].get("marks"):
            return copy.deepcopy(span["node"]["marks"])
    return []


def _apply_marks(nodes: list[dict], marks: list[dict]) -> None:
    """Add inherited marks to inserted text, without overriding its own."""
    if not marks:
        return
    for node in nodes:
        if node.get("type") != "text":
            continue
        own = node.get("marks") or []
        present = {m.get("type") for m in own}
        merged = own + [copy.deepcopy(m) for m in marks if m.get("type") not in present]
        if merged:
            node["marks"] = merged


def _merge_text_nodes(nodes: list[dict]) -> list[dict]:
    """Fuse adjacent text nodes carrying identical marks; drop empty ones."""
    out: list[dict] = []
    for node in nodes:
        if (
            out
            and node.get("type") == "text"
            and out[-1].get("type") == "text"
            and out[-1].get("marks") == node.get("marks")
        ):
            out[-1]["text"] = out[-1].get("text", "") + node.get("text", "")
            continue
        out.append(node)
    return [n for n in out if not (n.get("type") == "text" and not n.get("text"))]


# ---------------------------------------------------------------------------
# Markdown → ADF
# ---------------------------------------------------------------------------


_md = MarkdownIt("commonmark").enable("table").enable("strikethrough")


def markdown_to_adf(text: str) -> dict:
    """Convert Markdown (CommonMark + GFM tables/strikethrough) to ADF JSON.

    Plain text without any Markdown syntax round-trips as paragraph nodes,
    so callers can pass either rich Markdown or bare text.

    `@[accountId:Display Name]` becomes an ADF mention node (except inside
    code spans/blocks, where it stays literal).
    """
    tokens = _md.parse(text or "")
    content = _tokens_to_blocks(tokens)
    if not content:
        content = [{"type": "paragraph"}]
    return {"version": 1, "type": "doc", "content": content}


def markdown_inline_to_adf(text: str) -> list[dict]:
    """Convert a Markdown fragment to ADF *inline* nodes.

    Unlike `markdown_to_adf` this never produces block nodes, so the result can
    be spliced straight into a paragraph, heading, or task item. Block syntax
    in `text` (headings, lists, fences) stays literal.
    """
    if not text:
        return []
    nodes: list[dict] = []
    for tok in _md.parseInline(text, {}):
        if tok.type == "inline":
            nodes.extend(_inline_children(tok))
    return nodes


def _tokens_to_blocks(tokens: list[Token]) -> list[dict]:
    nodes: list[dict] = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        t = tok.type

        if t == "heading_open":
            level = int(tok.tag[1])
            inline_nodes = _inline_children(tokens[i + 1])
            node: dict = {"type": "heading", "attrs": {"level": level}}
            if inline_nodes:
                node["content"] = inline_nodes
            nodes.append(node)
            i += 3  # open, inline, close

        elif t == "paragraph_open":
            inline_nodes = _inline_children(tokens[i + 1])
            node = {"type": "paragraph"}
            if inline_nodes:
                node["content"] = inline_nodes
            nodes.append(node)
            i += 3

        elif t == "bullet_list_open":
            j = _find_close(tokens, i, "bullet_list_open", "bullet_list_close")
            items = _list_items(tokens[i + 1 : j])
            task_items = _try_task_list(items)
            if task_items is not None:
                nodes.append({
                    "type": "taskList",
                    "attrs": {"localId": str(uuid.uuid4())},
                    "content": task_items,
                })
            else:
                nodes.append({"type": "bulletList", "content": items})
            i = j + 1

        elif t == "ordered_list_open":
            j = _find_close(tokens, i, "ordered_list_open", "ordered_list_close")
            node = {"type": "orderedList", "content": _list_items(tokens[i + 1 : j])}
            start_raw = tok.attrGet("start")
            if start_raw is not None:
                start = int(start_raw)
                if start != 1:
                    node["attrs"] = {"order": start}
            nodes.append(node)
            i = j + 1

        elif t == "fence":
            lang_parts = (tok.info or "").strip().split(maxsplit=1)
            code = (tok.content or "").rstrip("\n")
            node = {"type": "codeBlock"}
            if lang_parts and lang_parts[0]:
                node["attrs"] = {"language": lang_parts[0]}
            if code:
                node["content"] = [{"type": "text", "text": code}]
            nodes.append(node)
            i += 1

        elif t == "code_block":
            code = (tok.content or "").rstrip("\n")
            node = {"type": "codeBlock"}
            if code:
                node["content"] = [{"type": "text", "text": code}]
            nodes.append(node)
            i += 1

        elif t == "blockquote_open":
            j = _find_close(tokens, i, "blockquote_open", "blockquote_close")
            inner = _tokens_to_blocks(tokens[i + 1 : j])
            if not inner:
                inner = [{"type": "paragraph"}]
            nodes.append({"type": "blockquote", "content": inner})
            i = j + 1

        elif t == "hr":
            nodes.append({"type": "rule"})
            i += 1

        elif t == "table_open":
            j = _find_close(tokens, i, "table_open", "table_close")
            nodes.append(_table_to_node(tokens[i + 1 : j]))
            i = j + 1

        else:
            # html_block, raw blocks, references — drop silently
            i += 1

    return nodes


def _find_close(tokens: list[Token], start: int, open_type: str, close_type: str) -> int:
    depth = 0
    for k in range(start, len(tokens)):
        if tokens[k].type == open_type:
            depth += 1
        elif tokens[k].type == close_type:
            depth -= 1
            if depth == 0:
                return k
    raise ValueError(f"Unbalanced {open_type}/{close_type} starting at {start}")


def _list_items(tokens: list[Token]) -> list[dict]:
    items: list[dict] = []
    i = 0
    n = len(tokens)
    while i < n:
        if tokens[i].type == "list_item_open":
            j = _find_close(tokens, i, "list_item_open", "list_item_close")
            inner = _tokens_to_blocks(tokens[i + 1 : j])
            if not inner:
                inner = [{"type": "paragraph"}]
            items.append({"type": "listItem", "content": inner})
            i = j + 1
        else:
            i += 1
    return items


_TASK_RE = re.compile(r"^\[([ xX])\](\s+|$)")


def _try_task_list(items: list[dict]) -> list[dict] | None:
    """Convert listItem nodes to taskItem nodes if every item is a GFM task.

    Returns None when any item is not a recognizable task — caller should keep
    the original bulletList. Items must have a single paragraph block whose
    first text node starts with `[ ]`, `[x]`, or `[X]`.
    """
    out: list[dict] = []
    for item in items:
        content = item.get("content") or []
        if len(content) != 1 or content[0].get("type") != "paragraph":
            return None
        inline = content[0].get("content") or []
        if not inline or inline[0].get("type") != "text":
            return None
        first_text = inline[0].get("text", "")
        m = _TASK_RE.match(first_text)
        if not m:
            return None
        state = "DONE" if m.group(1).lower() == "x" else "TODO"
        remaining = first_text[m.end():]
        if remaining:
            new_first = dict(inline[0])
            new_first["text"] = remaining
            new_inline = [new_first] + list(inline[1:])
        else:
            new_inline = list(inline[1:])
        task: dict = {
            "type": "taskItem",
            "attrs": {"localId": str(uuid.uuid4()), "state": state},
        }
        if new_inline:
            task["content"] = new_inline
        out.append(task)
    return out if out else None


def _table_to_node(tokens: list[Token]) -> dict:
    rows: list[dict] = []
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i].type
        if t == "thead_open":
            j = _find_close(tokens, i, "thead_open", "thead_close")
            rows.extend(_table_rows(tokens[i + 1 : j]))
            i = j + 1
        elif t == "tbody_open":
            j = _find_close(tokens, i, "tbody_open", "tbody_close")
            rows.extend(_table_rows(tokens[i + 1 : j]))
            i = j + 1
        else:
            i += 1
    return {"type": "table", "content": rows}


def _table_rows(tokens: list[Token]) -> list[dict]:
    rows: list[dict] = []
    i = 0
    n = len(tokens)
    while i < n:
        if tokens[i].type == "tr_open":
            j = _find_close(tokens, i, "tr_open", "tr_close")
            cells: list[dict] = []
            k = i + 1
            while k < j:
                t = tokens[k].type
                if t in ("th_open", "td_open"):
                    close_type = "th_close" if t == "th_open" else "td_close"
                    cell_type = "tableHeader" if t == "th_open" else "tableCell"
                    m = _find_close(tokens, k, t, close_type)
                    cell_blocks: list[dict] = []
                    for inner in tokens[k + 1 : m]:
                        if inner.type == "inline":
                            inline_nodes = _inline_children(inner)
                            para: dict = {"type": "paragraph"}
                            if inline_nodes:
                                para["content"] = inline_nodes
                            cell_blocks.append(para)
                    if not cell_blocks:
                        cell_blocks = [{"type": "paragraph"}]
                    cells.append({"type": cell_type, "content": cell_blocks})
                    k = m + 1
                else:
                    k += 1
            rows.append({"type": "tableRow", "content": cells})
            i = j + 1
        else:
            i += 1
    return rows


def _inline_children(inline_token: Token) -> list[dict]:
    return _inline_to_nodes(inline_token.children or [])


# Greedy first group splits on the LAST colon: account ids contain colons
# (e.g. "557058:f581…"), display names must not.
_MENTION_RE = re.compile(r"@\[([^\]]+):([^\]]+)\]")


def _inline_to_nodes(tokens: list[Token]) -> list[dict]:
    nodes: list[dict] = []
    active_marks: list[dict] = []

    def push_text(text: str) -> None:
        if not text:
            return
        node: dict = {"type": "text", "text": text}
        if active_marks:
            node["marks"] = [dict(m) for m in active_marks]
        nodes.append(node)

    def push_text_and_mentions(text: str) -> None:
        pos = 0
        for m in _MENTION_RE.finditer(text):
            push_text(text[pos : m.start()])
            nodes.append({
                "type": "mention",
                "attrs": {"id": m.group(1), "text": f"@{m.group(2)}"},
            })
            pos = m.end()
        push_text(text[pos:])

    for tok in tokens:
        t = tok.type
        if t == "text":
            push_text_and_mentions(tok.content)
        elif t == "code_inline":
            active_marks.append({"type": "code"})
            push_text(tok.content)
            _pop_mark(active_marks, "code")
        elif t == "strong_open":
            active_marks.append({"type": "strong"})
        elif t == "strong_close":
            _pop_mark(active_marks, "strong")
        elif t == "em_open":
            active_marks.append({"type": "em"})
        elif t == "em_close":
            _pop_mark(active_marks, "em")
        elif t == "s_open":
            active_marks.append({"type": "strike"})
        elif t == "s_close":
            _pop_mark(active_marks, "strike")
        elif t == "link_open":
            href = tok.attrGet("href") or ""
            mark: dict = {"type": "link", "attrs": {"href": href}}
            title = tok.attrGet("title")
            if title:
                mark["attrs"]["title"] = title
            active_marks.append(mark)
        elif t == "link_close":
            _pop_mark(active_marks, "link")
        elif t == "softbreak":
            push_text(" ")
        elif t == "hardbreak":
            nodes.append({"type": "hardBreak"})
        elif t == "image":
            alt = tok.content or tok.attrGet("alt") or ""
            if alt:
                push_text(alt)
        # html_inline, autolink (covered by link), emoji shortname etc. — dropped

    return nodes


def _pop_mark(stack: list[dict], mark_type: str) -> None:
    for i in range(len(stack) - 1, -1, -1):
        if stack[i].get("type") == mark_type:
            stack.pop(i)
            return
