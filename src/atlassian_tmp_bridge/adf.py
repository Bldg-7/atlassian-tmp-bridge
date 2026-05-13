"""Atlassian Document Format (ADF) <-> Markdown conversion."""

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
            parts.append(f"@{node.get('attrs', {}).get('text', 'unknown')}")
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


def _wrap_marks(text: str, marks: list) -> str:
    """Re-emit ADF inline marks as Markdown syntax.

    Wrapping order is innermost → outermost so that a re-parse produces the
    same mark set. `code` is innermost because Markdown code spans don't
    re-parse their contents; `link` is outermost because the link text can
    carry other formatting.
    """
    if not text or not marks:
        return text
    by_type = {m.get("type"): m for m in marks if isinstance(m, dict)}
    if "code" in by_type:
        text = f"`{text}`"
    if "strike" in by_type:
        text = f"~~{text}~~"
    if "em" in by_type:
        text = f"*{text}*"
    if "strong" in by_type:
        text = f"**{text}**"
    if "link" in by_type:
        href = (by_type["link"].get("attrs") or {}).get("href", "")
        if href:
            text = f"[{text}]({href})"
    return text


def _convert_table(rows: list) -> str:
    lines = []
    for row in rows:
        cells = []
        for cell in row.get("content", []):
            cells.append(_convert_nodes(cell.get("content", [])))
        lines.append(" | ".join(cells))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown → ADF
# ---------------------------------------------------------------------------


_md = MarkdownIt("commonmark").enable("table").enable("strikethrough")


def markdown_to_adf(text: str) -> dict:
    """Convert Markdown (CommonMark + GFM tables/strikethrough) to ADF JSON.

    Plain text without any Markdown syntax round-trips as paragraph nodes,
    so callers can pass either rich Markdown or bare text.
    """
    tokens = _md.parse(text or "")
    content = _tokens_to_blocks(tokens)
    if not content:
        content = [{"type": "paragraph"}]
    return {"version": 1, "type": "doc", "content": content}


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

    for tok in tokens:
        t = tok.type
        if t == "text":
            push_text(tok.content)
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
