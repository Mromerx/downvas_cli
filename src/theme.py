from rich.theme import Theme
from rich.console import Console


custom_theme = Theme({	# morado
    "primary": "bold #8B5CF6",
    "secondary": "#DDD6FE",
    "success": "bold #22C55E",
    "error": "bold #EF4444",
    "warning": "bold #F59E0B",
    "muted": "#9CA3AF",
    "module": "bold #C4B5FD",
    "prompt": "bold #DDD6FE",
    "progress.percentage": "#DDD6FE",
})


"""
custom_theme = Theme({	# naranjo
    "primary": "bold #F97316",
    "secondary": "#FED7AA",
    "success": "bold #22C55E",
    "error": "bold #EF4444",
    "warning": "bold #EAB308",
    "muted": "#9CA3AF",
    "module": "bold #FB923C",
    "prompt": "bold #FDBA74",
    "progress.percentage": "#FDBA74",
})
"""

"""
custom_theme = Theme({	# azul
    "primary": "bold #3B82F6",
    "secondary": "#BFDBFE",
    "success": "bold #22C55E",
    "error": "bold #EF4444",
    "warning": "bold #F59E0B",
    "muted": "#9CA3AF",
    "module": "bold #60A5FA",
    "prompt": "bold #93C5FD",
    "progress.percentage": "#93C5FD",
})
"""

console = Console(theme=custom_theme)
