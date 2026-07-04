from rich.theme import Theme
from rich.console import Console

custom_theme = Theme({
    "primary": "bold magenta",
    "secondary": "white",
    "success": "bold green",
    "error": "bold red",
    "warning": "bold yellow",
    "muted": "dim"
})

console = Console(theme=custom_theme)
