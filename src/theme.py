from rich.theme import Theme
from rich.console import Console

"""
custom_theme = Theme({
    "primary": "bold magenta",
    "secondary": "white",
    "success": "bold green",
    "error": "bold red",
    "warning": "bold yellow",
    "muted": "dim",
    "module": "white"
})
"""
custom_theme = Theme({
    "primary": "bold #A855F7",      # morado principal
    "secondary": "#D8B4FE",         # lavanda claro
    "success": "bold #22C55E",      # verde
    "error": "bold #EF4444",        # rojo
    "warning": "bold #F59E0B",      # ámbar
    "muted": "dim #7C3AED",         # morado tenue
    "module": "bold #818CF8",       # índigo claro
    "prompt": "default",            # estilo del [y/n] en prompts
    "progress.percentage": "#D8B4FE"  # porcentaje en barra de progreso
})



console = Console(theme=custom_theme)
