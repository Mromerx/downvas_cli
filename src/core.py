"""
Core module: Configuration, Exceptions, and Utilities.
"""
import os
from pathlib import Path
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# --- Exceptions ---
class DownVasError(Exception):
    pass

class CanvasAPIError(DownVasError):
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code

class CanvasAuthError(CanvasAPIError):
    pass

class RateLimitError(CanvasAPIError):
    pass

class CourseNotFoundError(CanvasAPIError):
    pass

class ConfigurationError(DownVasError):
    pass

class ConnectionError(DownVasError):
    pass

# --- Configuration ---
class Settings(BaseModel):
    canvas_url: str = Field(default="")
    api_token: str = Field(default="")
    download_dir: Path = Field(default_factory=lambda: Path.cwd() / "Descargas")

    @property
    def is_configured(self) -> bool:
        return bool(self.canvas_url and self.api_token and os.getenv("CANVAS_DOWNLOAD_DIR"))

    @classmethod
    def load(cls) -> "Settings":
        url = os.getenv("CANVAS_URL", "")
        token = os.getenv("CANVAS_TOKEN", "")
        dl_dir_str = os.getenv("CANVAS_DOWNLOAD_DIR")
        dl_dir = Path(dl_dir_str) if dl_dir_str else Path.cwd() / "Descargas"
        return cls(canvas_url=url, api_token=token, download_dir=dl_dir)

    def save(self) -> None:
        env_path = Path(".env")
        lines = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()
            
        def _update(key, val):
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={val}"
                    return
            lines.append(f"{key}={val}")
            
        _update("CANVAS_URL", self.canvas_url)
        _update("CANVAS_TOKEN", self.api_token)
        _update("CANVAS_DOWNLOAD_DIR", str(self.download_dir))
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        
        os.environ["CANVAS_URL"] = self.canvas_url
        os.environ["CANVAS_TOKEN"] = self.api_token
        os.environ["CANVAS_DOWNLOAD_DIR"] = str(self.download_dir)

    def update_url(self, new_url: str) -> None:
        new_url = new_url.strip()
        if not new_url:
            raise ConfigurationError("La URL de Canvas no puede estar vacia.")
        if not new_url.startswith(("http://", "https://")):
            raise ConfigurationError("La URL de Canvas debe comenzar con http:// o https://")
        self.canvas_url = new_url.rstrip("/")
        self.save()

    def update_token(self, new_token: str) -> None:
        new_token = new_token.strip()
        if not new_token:
            raise ConfigurationError("El token de acceso no puede estar vacio.")
        self.api_token = new_token
        self.save()

# --- Utilities ---
def human_readable_size(size_in_bytes: int) -> str:
    """Formats bytes into a human readable string."""
    if size_in_bytes is None:
        return "0 B"
    size = float(size_in_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"

def extract_course_id(input_str: str) -> int | None:
    cleaned = input_str.strip()
    if cleaned.isdigit():
        return int(cleaned)
    import re
    match = re.search(r"/courses/(\d+)", cleaned)
    if match:
        return int(match.group(1))
    return None

def extract_domain(url: str) -> str | None:
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        pass
    return None
