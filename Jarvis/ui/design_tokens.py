"""
Stitch Design Tokens — "User Profile and Voice Settings" project
================================================================
Centralised color, typography, spacing, and roundness constants
derived from the Stitch design system. Every UI file should import
from here — zero ad-hoc magic colours.

Stitch project metadata:
  • Color mode : DARK
  • Font        : Inter
  • Accent      : #135bec
  • Roundness   : 8 px
  • Saturation  : 3 (high)
  • Device      : Desktop 1280×1024
"""

# ── Palette ──────────────────────────────────────────────────────────────────

# Background layers (darkest → lightest)
BG_BASE           = "#0e1117"
BG_SURFACE        = "#161b22"
BG_SURFACE_ALT    = "#1c2333"
BG_ELEVATED       = "#21283b"

# Borders / Dividers
BORDER_DEFAULT    = "#2a3140"
BORDER_SUBTLE     = "#1e2530"
BORDER_ACCENT     = "#135bec"

# Text
TEXT_PRIMARY       = "#e6edf3"
TEXT_SECONDARY     = "#8b949e"
TEXT_MUTED         = "#484f58"
TEXT_ON_ACCENT     = "#ffffff"

# Accent
ACCENT             = "#135bec"
ACCENT_HOVER       = "#2d6ff2"
ACCENT_PRESSED     = "#0d47c4"
ACCENT_BG          = "rgba(19, 91, 236, 0.12)"
ACCENT_BG_HOVER    = "rgba(19, 91, 236, 0.20)"

# Semantic
SUCCESS            = "#3fb950"
SUCCESS_BG         = "rgba(63, 185, 80, 0.12)"
WARNING            = "#d29922"
WARNING_BG         = "rgba(210, 153, 34, 0.12)"
ERROR              = "#f85149"
ERROR_BG           = "rgba(248, 81, 73, 0.12)"
INFO               = "#58a6ff"

# Sidebar
SIDEBAR_BG         = "#0d1117"
SIDEBAR_HOVER      = "rgba(19, 91, 236, 0.10)"
SIDEBAR_ACTIVE     = "rgba(19, 91, 236, 0.18)"
SIDEBAR_INDICATOR  = ACCENT

# ── Typography ───────────────────────────────────────────────────────────────

FONT_FAMILY        = "Inter"
FONT_FAMILY_MONO   = "Consolas"

# Point sizes
FONT_SIZE_H1       = 22
FONT_SIZE_H2       = 17
FONT_SIZE_H3       = 14
FONT_SIZE_BODY     = 12
FONT_SIZE_SMALL    = 10
FONT_SIZE_CAPTION  = 9

# ── Spacing & Roundness ─────────────────────────────────────────────────────

RADIUS             = 8       # px  (Stitch "ROUND_EIGHT")
RADIUS_SM          = 4
RADIUS_LG          = 12
RADIUS_XL          = 16

SPACING_XS         = 4
SPACING_SM         = 8
SPACING_MD         = 12
SPACING_LG         = 16
SPACING_XL         = 24
SPACING_XXL        = 32

# ── Component Dimensions ────────────────────────────────────────────────────

SIDEBAR_WIDTH      = 220
HEADER_HEIGHT      = 48
CARD_MIN_WIDTH     = 280

# ── Shadows ─────────────────────────────────────────────────────────────────

SHADOW_COLOR       = "rgba(0, 0, 0, 0.35)"
SHADOW_BLUR        = 20
SHADOW_OFFSET_Y    = 4

# ── Pre-built Stylesheet Fragments ──────────────────────────────────────────

def card_style() -> str:
    """Reusable card (surface + border + radius)."""
    return f"""
        background: {BG_SURFACE};
        border: 1px solid {BORDER_DEFAULT};
        border-radius: {RADIUS}px;
        padding: {SPACING_LG}px;
    """

def card_hover_style() -> str:
    return f"""
        background: {BG_SURFACE_ALT};
        border: 1px solid {BORDER_ACCENT};
    """

def input_style() -> str:
    return f"""
        color: {TEXT_PRIMARY};
        background: {BG_BASE};
        border: 1px solid {BORDER_DEFAULT};
        border-radius: {RADIUS}px;
        padding: {SPACING_SM}px {SPACING_MD}px;
        font-family: '{FONT_FAMILY}';
        font-size: {FONT_SIZE_BODY}pt;
    """

def input_focus_style() -> str:
    return f"""
        border-color: {ACCENT};
        background: {BG_BASE};
    """

def button_primary_style() -> str:
    return f"""
        QPushButton {{
            color: {TEXT_ON_ACCENT};
            background: {ACCENT};
            border: none;
            border-radius: {RADIUS}px;
            padding: {SPACING_SM}px {SPACING_LG}px;
            font-family: '{FONT_FAMILY}';
            font-size: {FONT_SIZE_BODY}pt;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background: {ACCENT_HOVER};
        }}
        QPushButton:pressed {{
            background: {ACCENT_PRESSED};
        }}
    """

def button_secondary_style() -> str:
    return f"""
        QPushButton {{
            color: {TEXT_PRIMARY};
            background: {BG_SURFACE};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {RADIUS}px;
            padding: {SPACING_SM}px {SPACING_LG}px;
            font-family: '{FONT_FAMILY}';
            font-size: {FONT_SIZE_BODY}pt;
        }}
        QPushButton:hover {{
            background: {BG_SURFACE_ALT};
            border-color: {ACCENT};
            color: {ACCENT};
        }}
    """

def progress_bar_style(color: str = ACCENT) -> str:
    return f"""
        QProgressBar {{
            background: {BG_BASE};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {RADIUS_SM}px;
            text-align: center;
            color: {TEXT_SECONDARY};
            font-size: {FONT_SIZE_SMALL}pt;
            min-height: 8px;
            max-height: 8px;
        }}
        QProgressBar::chunk {{
            background: {color};
            border-radius: {RADIUS_SM}px;
        }}
    """

def scrollarea_style() -> str:
    return f"""
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 6px;
            margin: 4px 0;
        }}
        QScrollBar::handle:vertical {{
            background: {BORDER_DEFAULT};
            border-radius: 3px;
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {TEXT_MUTED};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
    """

def toggle_style() -> str:
    """Styled checkbox that looks like a toggle switch."""
    return f"""
        QCheckBox {{
            spacing: 8px;
            color: {TEXT_PRIMARY};
            font-family: '{FONT_FAMILY}';
            font-size: {FONT_SIZE_BODY}pt;
        }}
        QCheckBox::indicator {{
            width: 36px;
            height: 20px;
            border-radius: 10px;
            border: 1px solid {BORDER_DEFAULT};
            background: {BG_BASE};
        }}
        QCheckBox::indicator:checked {{
            background: {ACCENT};
            border-color: {ACCENT};
        }}
    """

def combobox_style() -> str:
    return f"""
        QComboBox {{
            color: {TEXT_PRIMARY};
            background: {BG_BASE};
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {RADIUS}px;
            padding: {SPACING_SM}px {SPACING_MD}px;
            font-family: '{FONT_FAMILY}';
            font-size: {FONT_SIZE_BODY}pt;
            min-height: 28px;
        }}
        QComboBox:hover {{
            border-color: {ACCENT};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid {TEXT_SECONDARY};
            margin-right: 8px;
        }}
        QComboBox QAbstractItemView {{
            background: {BG_SURFACE};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_DEFAULT};
            selection-background-color: {ACCENT};
            selection-color: {TEXT_ON_ACCENT};
            outline: none;
        }}
    """
