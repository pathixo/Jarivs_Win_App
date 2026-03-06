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
BG_BASE           = "#020617"  # Deepest Slate
BG_SURFACE        = "#0B1120"  # Slightly lighter Slate for sections
BG_SURFACE_ALT    = "#141C2F"  # Slate 800
BG_ELEVATED       = "#1E293B"  # Slate 700

# Borders / Dividers
BORDER_DEFAULT    = "rgba(255, 255, 255, 0.06)"
BORDER_STRONG     = "rgba(255, 255, 255, 0.12)"
BORDER_SUBTLE     = "rgba(255, 255, 255, 0.04)"
BORDER_ACCENT     = "#4F46E5"  # Indigo 600

# Text
TEXT_PRIMARY       = "#F8FAFC"  # Slate 50
TEXT_SECONDARY     = "#94A3B8"  # Slate 400
TEXT_MUTED         = "#64748B"  # Slate 500
TEXT_ON_ACCENT     = "#FFFFFF"

# Accent - Professional Indigo
ACCENT             = "#6366F1"  # Indigo 500
ACCENT_HOVER       = "#818CF8"  # Indigo 400
ACCENT_PRESSED     = "#4F46E5"  # Indigo 600
ACCENT_BG          = "rgba(99, 102, 241, 0.1)"
ACCENT_BG_HOVER    = "rgba(99, 102, 241, 0.15)"

# Semantic
SUCCESS            = "#10B981"  # Emerald 500
SUCCESS_BG         = "rgba(16, 185, 129, 0.1)"
WARNING            = "#F59E0B"  # Amber 500
WARNING_BG         = "rgba(245, 158, 11, 0.1)"
ERROR              = "#EF4444"  # Red 500
ERROR_BG           = "rgba(239, 68, 68, 0.1)"
INFO               = "#0EA5E9"  # Sky 500

# Sidebar
SIDEBAR_BG         = "rgba(2, 6, 23, 0.6)"
SIDEBAR_HOVER      = "rgba(255, 255, 255, 0.03)"
SIDEBAR_ACTIVE     = "rgba(99, 102, 241, 0.12)"
SIDEBAR_INDICATOR  = ACCENT


# ── Typography ───────────────────────────────────────────────────────────────

FONT_FAMILY        = "Inter"
FONT_FAMILY_MONO   = "JetBrains Mono"

# Point sizes
FONT_SIZE_H1       = 24
FONT_SIZE_H2       = 18
FONT_SIZE_H3       = 15
FONT_SIZE_BODY     = 11
FONT_SIZE_SMALL    = 10
FONT_SIZE_CAPTION  = 9

# ── Spacing & Roundness ─────────────────────────────────────────────────────

RADIUS             = 10      # px
RADIUS_SM          = 6
RADIUS_LG          = 14
RADIUS_XL          = 20

SPACING_XS         = 4
SPACING_SM         = 8
SPACING_MD         = 12
SPACING_LG         = 20
SPACING_XL         = 32
SPACING_XXL        = 48

# ── Component Dimensions ────────────────────────────────────────────────────

SIDEBAR_WIDTH      = 240
HEADER_HEIGHT      = 56
CARD_MIN_WIDTH     = 300

# ── Shadows ─────────────────────────────────────────────────────────────────

SHADOW_COLOR       = "rgba(0, 0, 0, 0.5)"
SHADOW_BLUR        = 30
SHADOW_OFFSET_Y    = 8

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
        border: 1px solid {ACCENT};
    """

def input_style() -> str:
    return f"""
        color: {TEXT_PRIMARY};
        background: rgba(0, 0, 0, 0.2);
        border: 1px solid {BORDER_DEFAULT};
        border-radius: {RADIUS_SM}px;
        padding: {SPACING_SM}px {SPACING_MD}px;
        font-family: '{FONT_FAMILY}';
        font-size: {FONT_SIZE_BODY}pt;
    """

def input_focus_style() -> str:
    return f"""
        border-color: {ACCENT};
        background: rgba(0, 0, 0, 0.3);
    """

def button_primary_style() -> str:
    return f"""
        QPushButton {{
            color: {TEXT_ON_ACCENT};
            background: {ACCENT};
            border: none;
            border-radius: {RADIUS_SM}px;
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
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {RADIUS_SM}px;
            padding: {SPACING_SM}px {SPACING_LG}px;
            font-family: '{FONT_FAMILY}';
            font-size: {FONT_SIZE_BODY}pt;
        }}
        QPushButton:hover {{
            background: rgba(255, 255, 255, 0.08);
            border-color: {TEXT_SECONDARY};
        }}
    """

def progress_bar_style(color: str = ACCENT) -> str:
    return f"""
        QProgressBar {{
            background: rgba(0, 0, 0, 0.2);
            border: none;
            border-radius: 3px;
            text-align: center;
            min-height: 6px;
            max-height: 6px;
        }}
        QProgressBar::chunk {{
            background: {color};
            border-radius: 3px;
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
            width: 8px;
            margin: 4px;
        }}
        QScrollBar::handle:vertical {{
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: rgba(255, 255, 255, 0.2);
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
    """

def toggle_style() -> str:
    """Styled checkbox that looks like a toggle switch."""
    return f"""
        QCheckBox {{
            spacing: 12px;
            color: {TEXT_PRIMARY};
            font-family: '{FONT_FAMILY}';
            font-size: {FONT_SIZE_BODY}pt;
        }}
        QCheckBox::indicator {{
            width: 40px;
            height: 22px;
            border-radius: 11px;
            border: 1px solid {BORDER_DEFAULT};
            background: rgba(0, 0, 0, 0.2);
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
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid {BORDER_DEFAULT};
            border-radius: {RADIUS_SM}px;
            padding: {SPACING_SM}px {SPACING_MD}px;
            font-family: '{FONT_FAMILY}';
            font-size: {FONT_SIZE_BODY}pt;
            min-height: 32px;
        }}
        QComboBox:hover {{
            border-color: {ACCENT};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 30px;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid {TEXT_SECONDARY};
            margin-right: 10px;
        }}
        QComboBox QAbstractItemView {{
            background: {BG_SURFACE};
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_DEFAULT};
            selection-background-color: {ACCENT_BG};
            selection-color: {ACCENT};
            outline: none;
            border-radius: {RADIUS_SM}px;
        }}
    """

