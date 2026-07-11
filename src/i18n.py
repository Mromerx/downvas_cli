"""
i18n module: Internationalization support via Python stdlib gettext.
Cross-platform: Windows, Linux, macOS.
"""
import os
import sys
import locale as locale_mod
import gettext
from pathlib import Path
from typing import Optional

_LOCALE_DIR = Path(__file__).resolve().parent.parent / "locales"
_TRANSLATIONS: Optional[gettext.NullTranslations] = None


def _detect_system_locale() -> str:
    """Detecta locale sin usar locale.getdefaultlocale()
    (deprecado desde 3.11, ELIMINADO en 3.13+)."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        if val:
            return val
    try:
        loc = locale_mod.getlocale()[0]
        if loc:
            return loc
    except Exception:
        pass
    return "en"


def _normalize_locale(locale_name: str) -> str:
    """Normaliza nombres de locale entre Windows y Unix.

    Unix:    es_ES.UTF-8       -> es
    Windows: Spanish_Spain.1252 -> es
    """
    lang = locale_name.split("_")[0].split("-")[0]
    return lang.lower() if lang else "en"


def setup_i18n(locale_name: Optional[str] = None) -> None:
    """Inicializa el sistema de traducción.

    Debe llamarse una sola vez, al inicio del programa, antes de
    cualquier uso de _().
    """
    global _TRANSLATIONS

    # Fuerza UTF-8 en consola de Windows para evitar romper acentos/ñ
    if sys.platform == "win32":
        for stream_name in ("stdout", "stderr"):
            stream = getattr(sys, stream_name)
            if hasattr(stream, "reconfigure"):
                try:
                    stream.reconfigure(encoding="utf-8")
                except Exception:
                    pass

    if not locale_name:
        locale_name = _detect_system_locale()

    lang = _normalize_locale(locale_name)
    mo_path = _LOCALE_DIR / lang / "LC_MESSAGES" / "messages.mo"

    if mo_path.exists():
        with open(mo_path, "rb") as f:
            _TRANSLATIONS = gettext.GNUTranslations(f)
    else:
        en_path = _LOCALE_DIR / "en" / "LC_MESSAGES" / "messages.mo"
        if en_path.exists():
            with open(en_path, "rb") as f:
                _TRANSLATIONS = gettext.GNUTranslations(f)
        else:
            _TRANSLATIONS = gettext.NullTranslations()


def _(message: str) -> str:
    """Traduce un mensaje. Inicializa i18n con locale del sistema si aún
    no fue inicializado."""
    if _TRANSLATIONS is None:
        setup_i18n()
    return _TRANSLATIONS.gettext(message)


# ---------------------------------------------------------------------------
# Sentinels: palabras clave de control que el usuario escribe en prompts.
# Siempre comparar con get_sentinel(), NUNCA contra el string traducido.
# ---------------------------------------------------------------------------
SENTINELS: dict[str, dict[str, str]] = {
    "es": {
        "finalizar": "finalizar",
        "credenciales": "credenciales",
        "config": "config",
    },
    "en": {
        "finalizar": "finish",
        "credenciales": "credentials",
        "config": "config",
    },
}


def get_sentinel(key: str, lang: str = "en") -> str:
    """Devuelve la palabra sentinel para el idioma dado."""
    return SENTINELS.get(lang, SENTINELS["en"]).get(key, key)
