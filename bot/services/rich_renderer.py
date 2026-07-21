"""Rich Message renderers — build InputRichMessage blocks for various bot views.

Uses the new Bot API 10.1+ Rich Messages system (paragraphs, headings, lists,
tables, slideshows, math, blockquotes, etc.). Falls back to plain HTML
messages if Rich Messages aren't supported in the chat.
"""
from __future__ import annotations

from typing import Any

# Block builders — each returns a dict matching Telegram's InputRichBlock schema.
# Spec: https://core.telegram.org/bots/api#inputrichblock


def paragraph(*rich_text_items: dict) -> dict:
    """A paragraph block containing one or more rich-text items."""
    return {"type": "paragraph", "rich_text": list(rich_text_items)}


def heading(text: str) -> dict:
    return {"type": "section_heading", "rich_text": [text_plain(text)]}


def footer(text: str) -> dict:
    return {"type": "footer", "rich_text": [text_plain(text)]}


def divider() -> dict:
    return {"type": "divider"}


def blockquote(*rich_text_items: dict) -> dict:
    return {"type": "blockquote", "rich_text": list(rich_text_items)}


def pullquote(*rich_text_items: dict) -> dict:
    return {"type": "pullquote", "rich_text": list(rich_text_items)}


def list_block(items: list[list[dict]]) -> dict:
    """An (unordered) list block. Each item is a list of rich-text items."""
    return {
        "type": "list",
        "items": [{"rich_text": it} for it in items],
    }


def table(headers: list[str], rows: list[list[str]]) -> dict:
    """Render a table block — perfect for leaderboards."""
    return {
        "type": "table",
        "header": [{"rich_text": [text_plain(h)]} for h in headers],
        "rows": [
            [{"rich_text": [text_plain(c)]} for c in row]
            for row in rows
        ],
    }


def slideshow(items: list[dict]) -> dict:
    """A slideshow block — each item should be a photo block."""
    return {"type": "slideshow", "items": items}


def photo_block(url: str, caption: list[dict] | None = None) -> dict:
    block = {"type": "photo", "photo": url}
    if caption:
        block["caption"] = {"rich_text": caption}
    return block


def math_block(expression: str) -> dict:
    """LaTeX math block — uses Bot API 10.1 MathematicalExpression."""
    return {
        "type": "mathematical_expression",
        "expression": expression,
        "format": "latex",
    }


def details(summary: list[dict], content: list[dict]) -> dict:
    """A collapsible details block (like <details>/<summary> in HTML)."""
    return {
        "type": "details",
        "summary": {"rich_text": summary},
        "content": content,
    }


# ─── Rich text leaf builders ─────────────────────────────────────

def text_plain(text: str) -> dict:
    return {"type": "plain", "text": text}


def text_bold(text: str) -> dict:
    return {"type": "bold", "text": text}


def text_italic(text: str) -> dict:
    return {"type": "italic", "text": text}


def text_underline(text: str) -> dict:
    return {"type": "underline", "text": text}


def text_strikethrough(text: str) -> dict:
    return {"type": "strikethrough", "text": text}


def text_spoiler(text: str) -> dict:
    return {"type": "spoiler", "text": text}


def text_code(text: str) -> dict:
    return {"type": "code", "text": text}


def text_mention(user_id: int, text: str) -> dict:
    return {"type": "text_mention", "user_id": user_id, "text": text}


def text_url(text: str, url: str) -> dict:
    return {"type": "url", "text": text, "url": url}


def text_math(expression: str) -> dict:
    """Inline LaTeX math."""
    return {"type": "mathematical_expression", "expression": expression, "format": "latex"}


def text_custom_emoji(emoji_id: str, fallback: str) -> dict:
    return {"type": "custom_emoji", "custom_emoji_id": emoji_id, "text": fallback}


def text_marked(text: str) -> dict:
    """Highlighted (yellow background) text."""
    return {"type": "marked", "text": text}


# ─── Convenience renderers for specific bot views ────────────────

def render_collection_slideshow(items: list[dict]) -> dict:
    """Build a slideshow of the user's collected characters.

    Each `items[i]` should be: {image_url, name, anime, rarity, rarity_score}
    """
    slides = []
    for it in items[:10]:  # cap at 10
        caption = [
            text_bold(it["name"]),
            text_plain("\n"),
            text_italic(it["anime"]),
            text_plain("  •  "),
            text_plain(rarity_emoji(it["rarity"]) + " " + it["rarity"]),
            text_plain(f"  (score: {it['rarity_score']})"),
        ]
        slides.append(photo_block(it["image_url"], caption=caption))
    return slideshow(slides)


def render_leaderboard_table(title: str, headers: list[str], rows: list[list[str]]) -> list[dict]:
    """Build blocks for a leaderboard view: heading + table + footer."""
    blocks = [
        heading(title),
        table(headers, rows),
        footer("Updated live • WaifuGrabberBot"),
    ]
    return blocks


def render_character_card(name: str, anime: str, rarity: str, score: int,
                           desc: str, image_url: str | None = None) -> list[dict]:
    """A detailed character card as Rich Message blocks."""
    blocks = []
    if image_url:
        blocks.append(photo_block(
            image_url,
            caption=[text_bold(name), text_plain("  "), text_italic(anime)],
        ))
    blocks.append(paragraph(
        text_plain(rarity_emoji(rarity) + " "),
        text_bold(rarity.upper()),
        text_plain(f"  •  Score: "),
        text_math(f"\\text{{{score}}}/100"),
    ))
    blocks.append(blockquote(text_italic(desc)))
    return blocks


def render_stats_with_math(stats: dict) -> list[dict]:
    """Stats panel showing catch-rate formula in LaTeX."""
    total = stats.get("total_attempts", 0)
    caught = stats.get("total_caught", 0)
    rate = (caught / total * 100) if total else 0
    return [
        heading("📊 Your Collection Stats"),
        list_block([
            [text_plain("Total caught: "), text_bold(str(caught))],
            [text_plain("Total attempts: "), text_bold(str(total))],
            [text_plain("Catch rate: "), text_bold(f"{rate:.1f}%")],
        ]),
        divider(),
        paragraph(text_plain("Catch rate formula:")),
        math_block(
            r"P(\text{catch}) = \frac{n_{\text{caught}}}{n_{\text{attempts}}} \times 100\%"
        ),
    ]


def rarity_emoji(rarity: str) -> str:
    return {
        "Mythic":    "🌟",
        "Legendary": "💎",
        "Epic":      "🔮",
        "Rare":      "⭐",
        "Uncommon":  "🟢",
        "Common":    "⚪",
    }.get(rarity, "❓")


def build_input_rich_message(blocks: list[dict]) -> dict:
    """Wrap blocks into an InputRichMessage payload for sendRichMessage."""
    return {"blocks": blocks}


# ─── HTML fallback (for clients that don't support Rich Messages) ──

def blocks_to_html(blocks: list[dict]) -> str:
    """Best-effort fallback: convert blocks to plain HTML."""
    out: list[str] = []
    for b in blocks:
        t = b.get("type")
        if t == "section_heading":
            out.append(f"<b>{_rich_to_html(b.get('rich_text', []))}</b>")
        elif t == "paragraph":
            out.append(_rich_to_html(b.get("rich_text", [])))
        elif t == "footer":
            out.append(f"<i>{_rich_to_html(b.get('rich_text', []))}</i>")
        elif t == "divider":
            out.append("— — — — —")
        elif t == "blockquote":
            out.append(f"<blockquote>{_rich_to_html(b.get('rich_text', []))}</blockquote>")
        elif t == "list":
            for it in b.get("items", []):
                out.append(f"• {_rich_to_html(it.get('rich_text', []))}")
        elif t == "table":
            headers = b.get("header", [])
            rows = b.get("rows", [])
            if headers:
                h = " | ".join(_rich_to_html(h.get("rich_text", [])) for h in headers)
                out.append(f"<b>{h}</b>")
            for r in rows:
                out.append(" | ".join(_rich_to_html(c.get("rich_text", [])) for c in r))
        elif t == "mathematical_expression":
            out.append(f"<code>{b.get('expression', '')}</code>")
    return "\n".join(out)


def _rich_to_html(items: list[dict] | str) -> str:
    if isinstance(items, str):
        return items
    parts = []
    for it in items:
        t = it.get("type", "plain")
        text = it.get("text", "")
        if t == "bold":
            parts.append(f"<b>{text}</b>")
        elif t == "italic":
            parts.append(f"<i>{text}</i>")
        elif t == "underline":
            parts.append(f"<u>{text}</u>")
        elif t == "strikethrough":
            parts.append(f"<s>{text}</s>")
        elif t == "spoiler":
            parts.append(f"<tg-spoiler>{text}</tg-spoiler>")
        elif t == "code":
            parts.append(f"<code>{text}</code>")
        elif t == "url":
            parts.append(f'<a href="{it.get("url", "")}">{text}</a>')
        elif t == "text_mention":
            parts.append(f'<a href="tg://user?id={it.get("user_id", 0)}">{text}</a>')
        elif t == "mathematical_expression":
            parts.append(f"<code>{it.get('expression', '')}</code>")
        else:
            parts.append(text)
    return "".join(parts)
