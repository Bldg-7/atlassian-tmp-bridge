"""Atlassian Document Format (ADF) <-> plain text conversion."""


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
            parts.append(node.get("text", ""))
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


def _convert_table(rows: list) -> str:
    lines = []
    for row in rows:
        cells = []
        for cell in row.get("content", []):
            cells.append(_convert_nodes(cell.get("content", [])))
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def text_to_adf(text: str) -> dict:
    """Convert plain text to ADF JSON."""
    paragraphs = []
    for line in text.split("\n"):
        if line.strip():
            paragraphs.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": line}],
            })
        else:
            paragraphs.append({"type": "paragraph", "content": []})

    return {"version": 1, "type": "doc", "content": paragraphs}
