"""
Application constants for Snappix.
"""

from __future__ import annotations

APP_NAME = "Snappix"
APP_FILE_EXTENSION = ".sfp"
PROJECT_FORMAT_NAME = "snappix-project"
PROJECT_FORMAT_VERSION = 3

ABOUT_AUTHOR = "Joachim Ruf"
ABOUT_WEBSITE = "loresoft.de"
ABOUT_GITHUB = "https://github.com/joruf/snappix"


def normalize_about_url(url: str) -> str:
    """
    Ensures an About-dialog URL has an http(s) scheme for opening in a browser.

    Args:
        url: Website or repository URL, with or without scheme.

    Returns:
        str: Absolute URL suitable for QDesktopServices / HTML href.
    """

    cleaned = str(url).strip()
    if not cleaned:
        return ""
    if cleaned.startswith(("http://", "https://")):
        return cleaned
    return f"https://{cleaned}"


def build_about_dialog_html(
    *,
    link_color: str | None = None,
) -> str:
    """
    Builds rich-text HTML for the About dialog, including clickable links.

    Args:
        link_color: Optional CSS color for anchors. Uses the active theme link
            color when omitted so links stay readable in dark and light mode.

    Returns:
        str: Qt rich-text HTML body for the About message box.
    """

    from src.theme import get_theme_colors

    colors = get_theme_colors()
    resolved_link = (link_color or colors.link).strip() or colors.link
    link_style = (
        f"color: {resolved_link}; text-decoration: underline; font-weight: 600;"
    )
    website_url = normalize_about_url(ABOUT_WEBSITE)
    github_url = normalize_about_url(ABOUT_GITHUB)
    return (
        f"<p><b>{APP_NAME}</b></p>"
        f"<p>Author: {ABOUT_AUTHOR}<br>"
        f'Website: <a href="{website_url}" style="{link_style}">{ABOUT_WEBSITE}</a><br>'
        f'GitHub: <a href="{github_url}" style="{link_style}">{ABOUT_GITHUB}</a></p>'
        "<p>Capture screenshots, annotate visuals, blur sensitive data, "
        "run OCR, and export fast.</p>"
    )
