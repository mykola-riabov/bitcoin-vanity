"""Color palettes for Qt themes."""

from __future__ import annotations

from typing import TypedDict

class ThemeColors(TypedDict):
    bg: str
    surface: str
    surface2: str
    sidebar: str
    card: str
    fg: str
    fg_dim: str
    accent: str
    accent_hover: str
    success: str
    danger: str
    warning: str
    border: str
    input_bg: str
    log_bg: str
    log_fg: str
    accent_btn_fg: str


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def _mix(a: str, b: str, t: float) -> str:
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    return _rgb_to_hex(
        int(ar + (br - ar) * t),
        int(ag + (bg - ag) * t),
        int(ab + (bb - ab) * t),
    )


def _luminance(hex_color: str) -> float:
    r, g, b = _hex_to_rgb(hex_color)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def _is_dark(hex_color: str) -> bool:
    return _luminance(hex_color) < 0.45


def _fill_theme(raw: dict[str, str]) -> ThemeColors:
    """Ensure derived keys exist for every palette."""
    bg = raw["bg"]
    dark = _is_dark(bg)
    card = raw.get("card")
    if not card:
        card = raw["surface"] if dark else _mix(raw["surface"], "#ffffff", 0.55)
    if "sidebar" in raw:
        sidebar = raw["sidebar"]
    elif dark:
        sidebar = _mix(bg, "#000000", 0.42)
    else:
        sidebar = _mix(raw["surface"], "#ffffff", 0.25)
    input_bg = raw.get("input_bg")
    if not input_bg:
        input_bg = _mix(card, "#000000", 0.12) if dark else "#ffffff"
    accent = raw["accent"]
    accent_btn_fg = raw.get("accent_btn_fg")
    if not accent_btn_fg:
        accent_btn_fg = "#ffffff" if _luminance(accent) < 0.62 else "#111111"
    return ThemeColors(
        bg=bg,
        surface=raw["surface"],
        surface2=raw["surface2"],
        sidebar=sidebar,
        card=card,
        fg=raw["fg"],
        fg_dim=raw["fg_dim"],
        accent=accent,
        accent_hover=raw["accent_hover"],
        success=raw["success"],
        danger=raw["danger"],
        warning=raw["warning"],
        border=raw["border"],
        input_bg=input_bg,
        log_bg=raw["log_bg"],
        log_fg=raw["log_fg"],
        accent_btn_fg=accent_btn_fg,
    )


THEMES: dict[str, ThemeColors] = {
    name: _fill_theme(raw)
    for name, raw in {
        "Bitcoin Dark": {
            "bg": "#1a1a1f",
            "surface": "#252530",
            "surface2": "#2f2f3a",
            "sidebar": "#121218",
            "card": "#252530",
            "fg": "#f5f5f5",
            "fg_dim": "#9a9aa8",
            "accent": "#f7931a",
            "accent_hover": "#ffb347",
            "success": "#2ecc71",
            "danger": "#e74c3c",
            "warning": "#f39c12",
            "border": "#3d3d4a",
            "input_bg": "#1e1e28",
            "log_bg": "#0e0e12",
            "log_fg": "#f5f5f5",
            "accent_btn_fg": "#1a1a1f",
        },
        "Cosmos Dark": {
            "bg": "#1a2332",
            "surface": "#243044",
            "surface2": "#2f3d52",
            "sidebar": "#141c28",
            "card": "#243044",
            "fg": "#ecf0f1",
            "fg_dim": "#95a5a6",
            "accent": "#2ecc71",
            "accent_hover": "#27ae60",
            "success": "#2ecc71",
            "danger": "#e74c3c",
            "warning": "#f39c12",
            "border": "#34495e",
            "input_bg": "#1e2a3a",
            "log_bg": "#121820",
            "log_fg": "#ecf0f1",
            "accent_btn_fg": "#ffffff",
        },
        "Mocha (dark)": {
            "bg": "#1e1e2e",
            "surface": "#313244",
            "surface2": "#45475a",
            "fg": "#cdd6f4",
            "fg_dim": "#a6adc8",
            "accent": "#89b4fa",
            "accent_hover": "#74c7ec",
            "success": "#a6e3a1",
            "danger": "#f38ba8",
            "warning": "#fab387",
            "border": "#585b70",
            "input_bg": "#313244",
            "log_bg": "#181825",
            "log_fg": "#cdd6f4",
            "accent_btn_fg": "#1e1e2e",
        },
        "Latte (light)": {
            "bg": "#eff1f5",
            "surface": "#e6e9ef",
            "surface2": "#dce0e8",
            "fg": "#4c4f69",
            "fg_dim": "#6c6f85",
            "accent": "#1e66f5",
            "accent_hover": "#3584e4",
            "success": "#40a02b",
            "danger": "#d20f39",
            "warning": "#fe640b",
            "border": "#bcc0cc",
            "input_bg": "#ffffff",
            "log_bg": "#ffffff",
            "log_fg": "#4c4f69",
            "accent_btn_fg": "#ffffff",
        },
        "Nord (dark)": {
            "bg": "#2e3440",
            "surface": "#3b4252",
            "surface2": "#434c5e",
            "fg": "#eceff4",
            "fg_dim": "#d8dee9",
            "accent": "#88c0d0",
            "accent_hover": "#8fbcbb",
            "success": "#a3be8c",
            "danger": "#bf616a",
            "warning": "#ebcb8b",
            "border": "#4c566a",
            "input_bg": "#3b4252",
            "log_bg": "#242933",
            "log_fg": "#eceff4",
            "accent_btn_fg": "#2e3440",
        },
        "Dracula (dark)": {
            "bg": "#282a36",
            "surface": "#383a59",
            "surface2": "#44475a",
            "fg": "#f8f8f2",
            "fg_dim": "#bd93f9",
            "accent": "#bd93f9",
            "accent_hover": "#ff79c6",
            "success": "#50fa7b",
            "danger": "#ff5555",
            "warning": "#ffb86c",
            "border": "#6272a4",
            "input_bg": "#383a59",
            "log_bg": "#1e1f29",
            "log_fg": "#f8f8f2",
            "accent_btn_fg": "#282a36",
        },
        "Forest (dark)": {
            "bg": "#1b2421",
            "surface": "#243029",
            "surface2": "#2f3d36",
            "fg": "#e0ece4",
            "fg_dim": "#9bb0a0",
            "accent": "#7fd99a",
            "accent_hover": "#9ae6b0",
            "success": "#7fd99a",
            "danger": "#f07178",
            "warning": "#e6c77a",
            "border": "#3d5248",
            "input_bg": "#243029",
            "log_bg": "#141a18",
            "log_fg": "#e0ece4",
            "accent_btn_fg": "#1b2421",
        },
        "Solarized (dark)": {
            "bg": "#002b36",
            "surface": "#073642",
            "surface2": "#0a4452",
            "fg": "#fdf6e3",
            "fg_dim": "#93a1a1",
            "accent": "#2aa198",
            "accent_hover": "#268bd2",
            "success": "#859900",
            "danger": "#dc322f",
            "warning": "#cb4b16",
            "border": "#586e75",
            "input_bg": "#073642",
            "log_bg": "#001e26",
            "log_fg": "#eee8d5",
            "accent_btn_fg": "#002b36",
        },
        "Solarized (light)": {
            "bg": "#fdf6e3",
            "surface": "#eee8d5",
            "surface2": "#e4ddc8",
            "fg": "#657b83",
            "fg_dim": "#839496",
            "accent": "#268bd2",
            "accent_hover": "#2aa198",
            "success": "#859900",
            "danger": "#dc322f",
            "warning": "#cb4b16",
            "border": "#93a1a1",
            "input_bg": "#ffffff",
            "log_bg": "#ffffff",
            "log_fg": "#586e75",
            "accent_btn_fg": "#ffffff",
        },
        "Gruvbox (dark)": {
            "bg": "#282828",
            "surface": "#3c3836",
            "surface2": "#504945",
            "fg": "#ebdbb2",
            "fg_dim": "#a89984",
            "accent": "#83a598",
            "accent_hover": "#8ec07c",
            "success": "#b8bb26",
            "danger": "#fb4934",
            "warning": "#fabd2f",
            "border": "#665c54",
            "input_bg": "#3c3836",
            "log_bg": "#1d2021",
            "log_fg": "#ebdbb2",
            "accent_btn_fg": "#282828",
        },
        "Gruvbox (light)": {
            "bg": "#fbf1c7",
            "surface": "#f2e5bc",
            "surface2": "#ebdbb2",
            "fg": "#3c3836",
            "fg_dim": "#665c54",
            "accent": "#076678",
            "accent_hover": "#427b58",
            "success": "#79740e",
            "danger": "#9d0006",
            "warning": "#b57614",
            "border": "#d5c4a1",
            "input_bg": "#ffffff",
            "log_bg": "#ffffff",
            "log_fg": "#3c3836",
            "accent_btn_fg": "#ffffff",
        },
        "Tokyo Night": {
            "bg": "#1a1b26",
            "surface": "#24283b",
            "surface2": "#2f3549",
            "fg": "#c0caf5",
            "fg_dim": "#565f89",
            "accent": "#7aa2f7",
            "accent_hover": "#2ac3de",
            "success": "#9ece6a",
            "danger": "#f7768e",
            "warning": "#e0af68",
            "border": "#414868",
            "input_bg": "#24283b",
            "log_bg": "#16161e",
            "log_fg": "#c0caf5",
            "accent_btn_fg": "#1a1b26",
        },
        "One Dark": {
            "bg": "#282c34",
            "surface": "#353b45",
            "surface2": "#3e4451",
            "fg": "#abb2bf",
            "fg_dim": "#5c6370",
            "accent": "#61afef",
            "accent_hover": "#56b6c2",
            "success": "#98c379",
            "danger": "#e06c75",
            "warning": "#e5c07b",
            "border": "#4b5263",
            "input_bg": "#353b45",
            "log_bg": "#21252b",
            "log_fg": "#abb2bf",
            "accent_btn_fg": "#282c34",
        },
        "Rose Pine": {
            "bg": "#191724",
            "surface": "#1f1d2e",
            "surface2": "#26233a",
            "fg": "#e0def4",
            "fg_dim": "#908caa",
            "accent": "#eb6f92",
            "accent_hover": "#c4a7e7",
            "success": "#9ccfd8",
            "danger": "#eb6f92",
            "warning": "#f6c177",
            "border": "#403d52",
            "input_bg": "#1f1d2e",
            "log_bg": "#12101a",
            "log_fg": "#e0def4",
            "accent_btn_fg": "#191724",
        },
        "Rose Pine Dawn (light)": {
            "bg": "#faf4ed",
            "surface": "#fffaf3",
            "surface2": "#f2e9e1",
            "fg": "#575279",
            "fg_dim": "#9893a5",
            "accent": "#286983",
            "accent_hover": "#56949f",
            "success": "#56949f",
            "danger": "#b4637a",
            "warning": "#ea9d34",
            "border": "#dfdad9",
            "input_bg": "#ffffff",
            "log_bg": "#ffffff",
            "log_fg": "#575279",
            "accent_btn_fg": "#ffffff",
        },
        "Monokai": {
            "bg": "#272822",
            "surface": "#3e3d32",
            "surface2": "#49483e",
            "fg": "#f8f8f2",
            "fg_dim": "#75715e",
            "accent": "#66d9ef",
            "accent_hover": "#a6e22e",
            "success": "#a6e22e",
            "danger": "#f92672",
            "warning": "#fd971f",
            "border": "#575757",
            "input_bg": "#3e3d32",
            "log_bg": "#1e1f1c",
            "log_fg": "#f8f8f2",
            "accent_btn_fg": "#272822",
        },
        "GitHub Dark": {
            "bg": "#0d1117",
            "surface": "#161b22",
            "surface2": "#21262d",
            "fg": "#c9d1d9",
            "fg_dim": "#8b949e",
            "accent": "#58a6ff",
            "accent_hover": "#79c0ff",
            "success": "#3fb950",
            "danger": "#f85149",
            "warning": "#d29922",
            "border": "#30363d",
            "input_bg": "#161b22",
            "log_bg": "#010409",
            "log_fg": "#c9d1d9",
            "accent_btn_fg": "#0d1117",
        },
        "GitHub Light": {
            "bg": "#ffffff",
            "surface": "#f6f8fa",
            "surface2": "#eaeef2",
            "fg": "#24292f",
            "fg_dim": "#57606a",
            "accent": "#0969da",
            "accent_hover": "#218bff",
            "success": "#1a7f37",
            "danger": "#cf222e",
            "warning": "#9a6700",
            "border": "#d0d7de",
            "input_bg": "#ffffff",
            "log_bg": "#ffffff",
            "log_fg": "#24292f",
            "accent_btn_fg": "#ffffff",
        },
        "Everforest": {
            "bg": "#2d353b",
            "surface": "#343f44",
            "surface2": "#3d484d",
            "fg": "#d3c6aa",
            "fg_dim": "#859289",
            "accent": "#7fbbb3",
            "accent_hover": "#83c092",
            "success": "#a7c080",
            "danger": "#e67e80",
            "warning": "#dbbc7f",
            "border": "#4f585e",
            "input_bg": "#343f44",
            "log_bg": "#232a2e",
            "log_fg": "#d3c6aa",
            "accent_btn_fg": "#2d353b",
        },
        "Ayu Mirage": {
            "bg": "#1f2430",
            "surface": "#272d3d",
            "surface2": "#303540",
            "fg": "#cbccc6",
            "fg_dim": "#707a8c",
            "accent": "#73d0ff",
            "accent_hover": "#95e6cb",
            "success": "#87d96c",
            "danger": "#f28779",
            "warning": "#ffd580",
            "border": "#3d424d",
            "input_bg": "#272d3d",
            "log_bg": "#171921",
            "log_fg": "#cbccc6",
            "accent_btn_fg": "#1f2430",
        },
        "Catppuccin Frappe": {
            "bg": "#303446",
            "surface": "#414559",
            "surface2": "#51576d",
            "fg": "#c6d0f5",
            "fg_dim": "#a5adce",
            "accent": "#8caaee",
            "accent_hover": "#99d1db",
            "success": "#a6d189",
            "danger": "#e78284",
            "warning": "#ef9f76",
            "border": "#626880",
            "input_bg": "#414559",
            "log_bg": "#292c3c",
            "log_fg": "#c6d0f5",
            "accent_btn_fg": "#303446",
        },
        "Catppuccin Macchiato": {
            "bg": "#24273a",
            "surface": "#363a4f",
            "surface2": "#494d64",
            "fg": "#cad3f5",
            "fg_dim": "#a5adcb",
            "accent": "#8aadf4",
            "accent_hover": "#91d7e3",
            "success": "#a6da95",
            "danger": "#ed8796",
            "warning": "#f5a97f",
            "border": "#5b6078",
            "input_bg": "#363a4f",
            "log_bg": "#1e2030",
            "log_fg": "#cad3f5",
            "accent_btn_fg": "#24273a",
        },
        "Midnight Cosmos": {
            "bg": "#0b0e14",
            "surface": "#131722",
            "surface2": "#1c2230",
            "fg": "#e6e6e6",
            "fg_dim": "#8b949e",
            "accent": "#6c5ce7",
            "accent_hover": "#00b894",
            "success": "#00b894",
            "danger": "#ff7675",
            "warning": "#fdcb6e",
            "border": "#2d3436",
            "input_bg": "#131722",
            "log_bg": "#050608",
            "log_fg": "#dfe6e9",
            "accent_btn_fg": "#0b0e14",
        },
    }.items()
}

DEFAULT_THEME = "Bitcoin Dark"


def theme_names() -> list[str]:
    return list(THEMES.keys())

