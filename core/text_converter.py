import re


def game_text_to_html(text: str) -> str:
    """Convert game-format text to QTextEdit-compatible HTML."""
    result = text

    # <color value='#rrggbb'>text</color> -> <span style="color: #rrggbb;">text</span>
    result = re.sub(
        r"""<color\s+value\s*=\s*['"]([^'"]+)['"]\s*>""",
        r"""<span style="color: \1;">""",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(r"</color>", "</span>", result, flags=re.IGNORECASE)

    # h1/h2/h3 tags are kept as-is — QTextEdit handles them natively

    # Empty <p></p> -> <p><br></p> so QTextEdit preserves them as blank lines
    result = re.sub(r"<p>\s*</p>", "<p><br></p>", result, flags=re.IGNORECASE)

    # Normalize <br/>
    result = re.sub(r"<br\s*/?>", "<br>", result, flags=re.IGNORECASE)

    # Fix attribute quotes: align='...' -> align="..."
    result = re.sub(r"align='([^']*)'", r'align="\1"', result, flags=re.IGNORECASE)

    return result


def html_to_game_text(html_text: str) -> str:
    """Convert QTextEdit HTML output back to game-format text.

    QTextEdit outputs complex HTML with inline styles. This function:
    1. Strips document wrappers
    2. Converts color spans -> <color> tags (full span matched)
    3. Converts bold spans -> <b> tags (full span matched)
    4. Strips Qt margin/indent styles from <p> tags
    """
    result = html_text

    # Strip document wrappers
    result = re.sub(r"<!DOCTYPE[^>]*>", "", result, flags=re.IGNORECASE)
    result = re.sub(r"<style[^>]*>.*?</style>", "", result, flags=re.IGNORECASE | re.DOTALL)
    result = re.sub(r"<html[^>]*>", "", result, flags=re.IGNORECASE)
    result = re.sub(r"</html>", "", result, flags=re.IGNORECASE)
    result = re.sub(r"<head[^>]*>.*?</head>", "", result, flags=re.IGNORECASE | re.DOTALL)
    result = re.sub(r"<body[^>]*>", "", result, flags=re.IGNORECASE)
    result = re.sub(r"</body>", "", result, flags=re.IGNORECASE)
    result = re.sub(r"<meta[^>]*>", "", result, flags=re.IGNORECASE)
    result = re.sub(r"<title[^>]*>.*?</title>", "", result, flags=re.IGNORECASE | re.DOTALL)

    # Convert full color spans: <span style="...color:#rrggbb;...">content</span>
    # -> <color value='#rrggbb'>content</color>
    def _convert_full_color_span(m):
        style = m.group(1)
        content = m.group(2)
        # Extract hex color from style string
        color_match = re.search(r"color:\s*#([0-9a-fA-F]+)", style)
        if color_match:
            hex_val = color_match.group(1)
            return "<color value='#%s'>%s</color>" % (hex_val, content)
        return m.group(0)  # No color found, return unchanged

    result = re.sub(
        r"""<span\s+style\s*=\s*"([^"]*)"\s*>(.*?)</span>""",
        _convert_full_color_span,
        result,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Convert full bold spans: <span style="...font-weight:700...">content</span>
    # -> <b>content</b>
    def _convert_full_bold_span(m):
        content = m.group(1)
        return "<b>%s</b>" % content

    result = re.sub(
        r"""<span\s+style\s*=\s*"[^"]*font-weight:\s*[67]00[^"]*"\s*>(.*?)</span>""",
        _convert_full_bold_span,
        result,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Strip any remaining spans (shouldn't be any, but just in case)
    result = re.sub(r"<span[^>]*>", "", result, flags=re.IGNORECASE)
    result = re.sub(r"</span>", "", result, flags=re.IGNORECASE)

    # Clean heading tags: <h1 style="...">text</h1> -> <h1>text</h1>
    def _clean_heading(m):
        tag = m.group(1)
        return "<%s>" % tag

    result = re.sub(r"<(h[123])\s+[^>]*>", _clean_heading, result, flags=re.IGNORECASE)

    # Wrap headings in <p> for game format compatibility
    def _wrap_heading_in_p(m):
        p_open = m.group(1)
        tag = m.group(2)
        inner = m.group(3)
        align_match = re.search(r"""align=["']([^"']*)["']""", p_open)
        align_attr = ' align="%s"' % align_match.group(1) if align_match else ""
        return "<p%s><%s>%s</%s></p>" % (align_attr, tag, inner, tag)

    # Match headings inside existing <p> tags (strip the old <p>, rewrap)
    result = re.sub(
        r"<p((?:\s[^>]*)?)>\s*<(h[123])>(.*?)</\2>\s*</p>",
        _wrap_heading_in_p,
        result,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Wrap completely bare headings
    result = re.sub(
        r"<(h[123])>(.+?)</\1>",
        _wrap_heading_in_p,
        result,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Clean <p> tags: keep only align, remove Qt margin/indent styles
    def _clean_p_tag(m):
        tag = m.group(0)
        align_match = re.search(r"""align=["']([^"']*)["']""", tag)
        align = ' align="%s"' % align_match.group(1) if align_match else ""
        return "<p%s>" % align

    result = re.sub(r"<p\s+[^>]*>", _clean_p_tag, result, flags=re.IGNORECASE)

    # <br /> -> <br>
    result = re.sub(r"<br\s*/?>", "<br>", result, flags=re.IGNORECASE)

    # <p><br></p> -> <p></p> (empty line marker for game format)
    result = re.sub(r"<p>\s*<br>\s*</p>", "<p></p>", result, flags=re.IGNORECASE)

    # Fix attribute quotes: align="..." -> align='...'
    result = re.sub(r'align="([^"]*)"', r"align='\1'", result, flags=re.IGNORECASE)

    # Clean up whitespace on lines
    lines = result.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            cleaned.append(stripped)
        else:
            cleaned.append("")
    result = "\n".join(cleaned)

    return result.strip()
