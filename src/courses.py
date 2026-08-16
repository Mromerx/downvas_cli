"""
Courses module: Canvas HTTP Client (Data), Tree Models (Domain), and Rich Tree View (Presentation).
"""
import time
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict
import requests

from rich.tree import Tree

from src.core import (
    CanvasAPIError,
    CanvasAuthError,
    RateLimitError,
    CourseNotFoundError,
    ConnectionError as CanvasConnectionError,
    human_readable_size
)
from src.i18n import _

@dataclass
class CanvasCourse:
    id: int
    name: str

@dataclass
class CanvasFolder:
    id: int
    parent_folder_id: Optional[int]
    name: str
    full_name: str
    is_root: bool

@dataclass
class CanvasFile:
    id: int
    folder_id: Optional[int]
    display_name: str
    module_name: Optional[str]
    size: Optional[int]
    url: Optional[str]
    locked: bool = False
    hidden: bool = False
    module_id: Optional[int] = None  # ID único del módulo Canvas para evitar colisiones de ruta
    page_name: Optional[str] = None  # Título de la página donde se enlaza el archivo
    page_id: Optional[int] = None    # ID único de la página para evitar colisiones de ruta
    source: str = "none"             # "module" | "page" | "folder" | "none"
    course_id: Optional[int] = None  # Curso al que pertenece el archivo

    @property
    def extension(self) -> str:
        if "." in self.display_name:
            return "." + self.display_name.split(".")[-1].lower()
        return ""

class CourseTree:
    """Represents the hierarchical structure of a course."""
    def __init__(self, course: CanvasCourse):
        self.course = course
        self.files: Dict[int, CanvasFile] = {}
        self.folders: Dict[int, CanvasFolder] = {}
        
        self.root_folder_id: Optional[int] = None
        self.subfolders_map: Dict[int, List[int]] = defaultdict(list)
        self.folder_files_map: Dict[int, List[CanvasFile]] = defaultdict(list)

    def add_folder(self, folder: CanvasFolder) -> None:
        self.folders[folder.id] = folder
        if folder.is_root:
            self.root_folder_id = folder.id

    def add_file(self, file: CanvasFile) -> None:
        self.files[file.id] = file

    def build_hierarchy(self) -> None:
        """Populates hierarchy maps."""
        self.subfolders_map.clear()
        self.folder_files_map.clear()
        
        for folder in self.folders.values():
            if folder.parent_folder_id is not None:
                self.subfolders_map[folder.parent_folder_id].append(folder.id)
                
        for file in self.files.values():
            if file.folder_id is not None:
                self.folder_files_map[file.folder_id].append(file)

    def get_all_files(self) -> List[CanvasFile]:
        return list(self.files.values())

    def get_files_by_extension(self, ext: str) -> List[CanvasFile]:
        ext = ext.lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        return [f for f in self.files.values() if f.extension == ext]

    def get_file_download_path(self, file_id: int, base_dir: Path) -> Path:
        file = self.files.get(file_id)
        if not file:
            return base_dir / "unknown"
            
        def clean_name(name: str) -> str:
            import re
            return re.sub(r'[\\/*?:"<>|]', "", name).strip()
            
        course_folder = clean_name(self.course.name)
        file_name = clean_name(file.display_name)
        
        if file.page_name and file.page_id is not None:
            d = clean_name(file.page_name)
            return base_dir / course_folder / f"{d} ({file.page_id})" / file_name

        if file.module_name and file.module_id:
            d = clean_name(file.module_name)
            return base_dir / course_folder / f"{d} ({file.module_id})" / file_name

        if file.module_name:
            # Fallback sin ID (no debería ocurrir en condiciones normales)
            return base_dir / course_folder / clean_name(file.module_name) / file_name

        if file.folder_id and self.folders:
            path_parts = []
            current_folder_id = file.folder_id
            while current_folder_id:
                folder = self.folders.get(current_folder_id)
                if not folder:
                    break
                d = clean_name(folder.name)
                path_parts.insert(0, f"{d} ({folder.id})")
                current_folder_id = folder.parent_folder_id
            if path_parts:
                return base_dir / course_folder / Path(*path_parts) / file_name

        return base_dir / course_folder / file_name

    def find_file_by_name(self, name: str) -> List[CanvasFile]:
        query = name.lower()
        return [f for f in self.files.values() if query in f.display_name.lower()]

    def find_file_by_path(self, path_str: str) -> Optional[CanvasFile]:
        query = path_str.lower().strip()
        for f in self.files.values():
            if f.display_name.lower() == query:
                return f
        return None


def _is_http_forbidden(e: Exception) -> bool:
    # 401/403: sin permiso. 404: endpoint/sección no disponible. En ambos casos
    # la sección se omite y el resto del curso se carga igual.
    if isinstance(e, CanvasAPIError):
        return e.status_code in (401, 403, 404)
    if isinstance(e, requests.HTTPError):
        resp = getattr(e, "response", None)
        if resp is not None:
            return resp.status_code in (401, 403, 404)
    return False


def extract_file_links_from_html(html: str, course_id: int) -> List[Tuple[int, Optional[str]]]:
    """Extrae (file_id, nombre_conocido) de enlaces a archivos dentro de HTML.

    El nombre conocido proviene del atributo ``title`` o del texto del enlace
    (``<a ...>texto</a>``) y se usa como respaldo cuando la API no devuelve el
    archivo por ID.
    """
    import re
    from html import unescape

    results: List[Tuple[int, Optional[str]]] = []
    seen: set = set()

    id_patterns = [
        re.compile(rf"/courses/{course_id}/files/(\d+)", re.IGNORECASE),
        re.compile(rf"/api/v1/courses/{course_id}/files/(\d+)", re.IGNORECASE),
        re.compile(r"/api/v1/files/(\d+)", re.IGNORECASE),
        re.compile(r"(?<!\d)/files/(\d+)", re.IGNORECASE),
    ]

    def push(fid: int, name: Optional[str]) -> None:
        if fid and fid not in seen:
            seen.add(fid)
            results.append((fid, name))

    def ids_in(text: str, name: Optional[str]) -> None:
        for pat in id_patterns:
            for m in pat.finditer(text):
                push(int(m.group(1)), name)

    attr_re = re.compile(
        r'([\w:-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s"\'=<>`]+))',
        re.IGNORECASE,
    )

    for m in re.finditer(r"<a\b[^>]*>(.*?)</a>", html, re.IGNORECASE | re.DOTALL):
        attrs: Dict[str, str] = {}
        for am in attr_re.finditer(m.group(0)):
            key = am.group(1).lower()
            value = am.group(2) or am.group(3) or am.group(4) or ""
            if key not in attrs:
                attrs[key] = value
        href = attrs.get("href", "")
        title = attrs.get("title")
        inner = re.sub(r"<[^>]+>", "", m.group(1))
        inner = unescape(inner).strip()
        name = (title or inner or None) if (title or inner) else None
        if href:
            ids_in(href, name)

    # Ocurrencias fuera de <a> (p. ej. <img> o src directos) — sin nombre conocido.
    ids_in(html, None)

    return results


def extract_file_ids_from_html(html: str, course_id: int) -> List[int]:
    """Backward-compatible helper: solo devuelve los IDs de archivos enlazados."""
    return [fid for fid, _ in extract_file_links_from_html(html, course_id)]

class CanvasAPIClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        # Canvas exige un User-Agent explícito (enforcement de la plataforma desde 2026).
        self.session.headers.update({"User-Agent": "DownVas/1.0 (Canvas Downloader)"})

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        try:
            response = self.session.request(method, url, **kwargs)
            remaining = response.headers.get("X-Rate-Limit-Remaining")
            if remaining:
                try:
                    if float(remaining) < 10.0:
                        time.sleep(2.0)
                except ValueError:
                    pass

            if response.status_code == 200:
                return response
            elif response.status_code == 401:
                raise CanvasAuthError(_("Token de acceso invalido o expirado."), status_code=401)
            elif response.status_code == 404:
                raise CourseNotFoundError(_("El curso no fue encontrado."), status_code=404)
            elif response.status_code in (403, 429):
                err_msg = response.text.lower()
                if "rate limit" in err_msg or response.status_code == 429:
                    time.sleep(5.0)
                    response = self.session.request(method, url, **kwargs)
                    if response.status_code == 200:
                        return response
                    raise RateLimitError(_("Limite de solicitudes alcanzado."), status_code=response.status_code)
                raise CanvasAPIError(f"{_('Acceso denegado')} ({response.status_code}): {response.text}", status_code=response.status_code)
            else:
                raise CanvasAPIError(f"{_('Error HTTP')} {response.status_code}", status_code=response.status_code)

        except requests.exceptions.ConnectionError as e:
            raise CanvasConnectionError(f"{_('No se pudo establecer conexion')}: {e}")
        except requests.RequestException as e:
            if isinstance(e, CanvasAPIError):
                raise
            raise CanvasAPIError(f"{_('Error de red inesperado')}: {e}")

    def verify_authentication(self) -> None:
        self._request("GET", f"{self.base_url}/api/v1/users/self")

    def fetch_course_name(self, course_id: int) -> str:
        data = self.get_course(course_id)
        return data.get("name") or data.get("course_code") or f"Curso {course_id}"

    def get_course(self, course_id: int) -> Dict[str, Any]:
        resp = self._request("GET", f"{self.base_url}/api/v1/courses/{course_id}")
        return resp.json()

    def get_modules(self, course_id: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/courses/{course_id}/modules"
        modules = []
        while url:
            r = self.session.get(url, params=[("include[]", "items"), ("include[]", "content_details")])
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                modules.extend(data)
            url = self._get_next_link(r)
        return modules

    def get_folders(self, course_id: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/courses/{course_id}/folders"
        folders = []
        while url:
            r = self._request("GET", url)
            data = r.json()
            if isinstance(data, list):
                folders.extend(data)
            url = self._get_next_link(r)
        return folders

    def get_files(self, course_id: int) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/v1/courses/{course_id}/files"
        files = []
        while url:
            r = self._request("GET", url)
            data = r.json()
            if isinstance(data, list):
                files.extend(data)
            url = self._get_next_link(r)
        return files

    def get_pages(self, course_id: int) -> List[Dict[str, Any]]:
        """Lista las páginas del curso incluyendo el cuerpo HTML para extraer enlaces."""
        url = f"{self.base_url}/api/v1/courses/{course_id}/pages"
        pages = []
        try:
            while url:
                r = self._request("GET", url, params=[("include[]", "body"), ("per_page", "100")])
                data = r.json()
                if isinstance(data, list):
                    pages.extend(data)
                url = self._get_next_link(r)
        except CourseNotFoundError:
            return []
        return pages

    def get_file_metadata(self, course_id: int, file_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene metadatos de un archivo. Prioriza el endpoint con contexto de curso
        (cercano al scope típico de un token) y hace fallback al endpoint global."""
        for url_fmt in (
            f"{self.base_url}/api/v1/courses/{course_id}/files/{file_id}",
            f"{self.base_url}/api/v1/files/{file_id}",
        ):
            try:
                r = self._request("GET", url_fmt)
                return r.json()
            except (CanvasAPIError, requests.HTTPError):
                continue
        return None

    def _paginated(self, url: str, params: Optional[List[Tuple[str, str]]] = None) -> List[Dict[str, Any]]:
        """Recorre todas las páginas de un endpoint, aplicando params solo a la primera petición."""
        items: List[Dict[str, Any]] = []
        first = True
        while url:
            kwargs = {}
            if params and first:
                kwargs["params"] = params
            first = False
            r = self._request("GET", url, **kwargs)
            data = r.json()
            if isinstance(data, list):
                items.extend(data)
            url = self._get_next_link(r)
        return items

    def _extract_rich_content_files(self, tree: CourseTree, course_id: int) -> None:
        """Busca archivos enlazados en todo el rich content del curso (páginas,
        tareas, discusiones, anuncios y sílabo) y los agrega al árbol si faltan.

        Cada origen no disponible (403/404) se omite sin romper el resto.
        """
        # (etiqueta, html, page_id sintético para agrupar/desambiguar)
        sources: List[Tuple[str, str, int]] = []

        try:
            for page in self.get_pages(course_id):
                body = page.get("body") or ""
                if body:
                    sources.append((page.get("title") or _("Página"), body, page.get("page_id") or 0))
        except (CanvasAPIError, requests.HTTPError) as e:
            if not _is_http_forbidden(e): raise

        try:
            for a in self._paginated(
                f"{self.base_url}/api/v1/courses/{course_id}/assignments",
                [("per_page", "100")],
            ):
                desc = a.get("description") or ""
                if desc:
                    sources.append((a.get("name") or _("Tarea"), desc, a.get("id") or 0))
        except (CanvasAPIError, requests.HTTPError) as e:
            if not _is_http_forbidden(e): raise

        for only_ann in (None, "true"):
            try:
                qp = [("per_page", "100")]
                if only_ann:
                    qp.append(("only_announcements", "true"))
                for d in self._paginated(
                    f"{self.base_url}/api/v1/courses/{course_id}/discussion_topics",
                    qp,
                ):
                    msg = d.get("message") or ""
                    if msg:
                        sources.append((d.get("title") or _("Discusión"), msg, d.get("id") or 0))
            except (CanvasAPIError, requests.HTTPError) as e:
                if not _is_http_forbidden(e): raise

        try:
            r = self._request(
                "GET",
                f"{self.base_url}/api/v1/courses/{course_id}",
                params=[("include[]", "syllabus_body")],
            )
            sb = r.json().get("syllabus_body") or ""
            if sb:
                sources.append((_("Sílabo"), sb, -1))
        except (CanvasAPIError, requests.HTTPError) as e:
            if not _is_http_forbidden(e): raise

        for label, html, pid in sources:
            self._add_files_from_html(tree, course_id, label, html, pid)

    def ensure_file_in_tree(self, tree: CourseTree, course_id: int, file_id: int) -> bool:
        """Garantiza que un archivo conocido por su ID aparezca en el árbol aunque
        no haya sido detectado por módulos/carpetas/rich content (p. ej. si el
        usuario pegó una URL de archivo)."""
        if file_id in tree.files:
            return True
        meta = self.get_file_metadata(course_id, file_id)
        if not meta:
            return False
        tree.add_file(CanvasFile(
            id=file_id,
            folder_id=meta.get("folder_id"),
            display_name=(meta.get("display_name") or meta.get("filename") or _("archivo")),
            module_name=None,
            size=meta.get("size"),
            url=meta.get("url"),
            locked=meta.get("locked_for_user", False),
            hidden=meta.get("hidden_for_user", False),
            source="none",
            course_id=course_id,
        ))
        tree.build_hierarchy()
        return True

    def _add_files_from_html(
        self,
        tree: CourseTree,
        course_id: int,
        label: str,
        html: str,
        pid: int,
        module_name: Optional[str] = None,
        module_id: Optional[int] = None,
    ) -> None:
        """Extrae los archivos enlazados en un bloque HTML (páginas, tareas,
        discusiones, items de módulo) y los agrega al árbol si aún no existen."""
        for fid, anchor_name in extract_file_links_from_html(html, course_id):
            if fid in tree.files:
                continue
            meta = self.get_file_metadata(course_id, fid)
            if meta:
                tree.add_file(CanvasFile(
                    id=fid,
                    folder_id=meta.get("folder_id"),
                    display_name=(meta.get("display_name") or meta.get("filename") or anchor_name or _("archivo")),
                    module_name=module_name,
                    module_id=module_id,
                    size=meta.get("size"),
                    url=meta.get("url"),
                    locked=meta.get("locked_for_user", False),
                    hidden=meta.get("hidden_for_user", False),
                    page_name=label,
                    page_id=pid,
                    source="page",
                    course_id=course_id,
                ))
            else:
                # Sin metadatos: aun así se muestra con el nombre del enlace.
                tree.add_file(CanvasFile(
                    id=fid,
                    folder_id=None,
                    display_name=anchor_name or _("archivo"),
                    module_name=module_name,
                    module_id=module_id,
                    size=None,
                    url=None,
                    page_name=label,
                    page_id=pid,
                    source="page",
                    course_id=course_id,
                ))

    def get_module_item(self, course_id: int, item_id: int) -> Dict[str, Any]:
        """Obtiene un item de módulo por su ID. La respuesta puede venir como el
        item directamente o envuelta en {items:[{current,...}], modules:[...]}."""
        r = self._request(
            "GET",
            f"{self.base_url}/api/v1/courses/{course_id}/modules/items/{item_id}",
        )
        data = r.json()
        if not isinstance(data, dict):
            return {}

        modules_by_id: Dict[str, str] = {}
        for m in data.get("modules") or []:
            if isinstance(m, dict):
                mid = str(m.get("id"))
                if mid and not modules_by_id.get(mid):
                    modules_by_id[mid] = m.get("name") or ""

        item: Dict[str, Any] = data
        if isinstance(data.get("items"), list):
            for wrapper in data["items"]:
                if isinstance(wrapper, dict) and isinstance(wrapper.get("current"), dict):
                    item = wrapper["current"]
                    break
            else:
                item = data["items"][0] if data["items"] and isinstance(data["items"][0], dict) else data
        elif isinstance(data.get("current"), dict):
            item = data["current"]

        mid = str(item.get("module_id") or "")
        if mid and not item.get("module_name") and modules_by_id.get(mid):
            item["module_name"] = modules_by_id[mid]
        return item

    def get_page(self, course_id: int, page_ref: str) -> Dict[str, Any]:
        """Obtiene una sola página con su cuerpo HTML. Acepta page_id,
        page_url (slug) o 'front_page'."""
        ref = str(page_ref).strip("/")
        url = f"{self.base_url}/api/v1/courses/{course_id}/pages/{requests.utils.quote(ref, safe='-._~')}"
        r = self._request("GET", url, params=[("include[]", "body")])
        return r.json()

    def get_assignment(self, course_id: int, assignment_id: int) -> Dict[str, Any]:
        r = self._request("GET", f"{self.base_url}/api/v1/courses/{course_id}/assignments/{assignment_id}")
        return r.json()

    def get_discussion_topic(self, course_id: int, topic_id: int) -> Dict[str, Any]:
        r = self._request("GET", f"{self.base_url}/api/v1/courses/{course_id}/discussion_topics/{topic_id}")
        return r.json()

    def get_quiz(self, course_id: int, quiz_id: int) -> Dict[str, Any]:
        r = self._request("GET", f"{self.base_url}/api/v1/courses/{course_id}/quizzes/{quiz_id}")
        return r.json()

    def resolve_page_item(
        self,
        tree: CourseTree,
        course_id: int,
        item: Dict[str, Any],
        module_name: Optional[str] = None,
        module_id: Optional[int] = None,
    ) -> None:
        """Resuelve un item de módulo tipo Page: obtiene el cuerpo de la página
        y agrega al árbol los archivos que enlaza (aun si la página no aparece
        en el índice global de páginas)."""
        page_ref = item.get("page_url") or item.get("content_id")
        if not page_ref:
            return
        try:
            page = self.get_page(course_id, str(page_ref))
        except (CanvasAPIError, requests.HTTPError):
            return
        body = (page or {}).get("body") or ""
        if not body:
            return
        pid = (page.get("page_id") or item.get("content_id") or 0)
        label = item.get("title") or page.get("title") or _("Página")
        self._add_files_from_html(tree, course_id, label, body, pid, module_name, module_id)

    def _resolve_content_item(
        self,
        tree: CourseTree,
        course_id: int,
        item: Dict[str, Any],
        item_type: str,
        module_name: Optional[str] = None,
    ) -> None:
        """Resuelve items de módulo Assignment/Discussion/Quiz: escanea su HTML
        (description/message) y también el array de attachments adjuntos."""
        content_id = item.get("content_id")
        if not content_id:
            return
        label = item.get("title") or _("Contenido")
        pid = content_id
        module_id = item.get("module_id")
        try:
            if item_type == "Assignment":
                obj = self.get_assignment(course_id, content_id)
                html = (obj or {}).get("description") or ""
                attachments = (obj or {}).get("attachments") or []
            elif item_type == "Discussion":
                obj = self.get_discussion_topic(course_id, content_id)
                html = (obj or {}).get("message") or ""
                attachments = (obj or {}).get("attachments") or []
            else:  # Quiz
                obj = self.get_quiz(course_id, content_id)
                html = (obj or {}).get("description") or ""
                attachments = []
        except (CanvasAPIError, requests.HTTPError):
            return

        if html:
            self._add_files_from_html(tree, course_id, label, html, pid, module_name, module_id)
        for att in attachments:
            fid = att.get("id") if isinstance(att, dict) else None
            if not fid or fid in tree.files:
                continue
            tree.add_file(CanvasFile(
                id=fid,
                folder_id=att.get("folder_id"),
                display_name=(att.get("display_name") or att.get("filename") or _("archivo")),
                module_name=module_name,
                module_id=module_id,
                size=att.get("size"),
                url=att.get("url"),
                locked=att.get("locked_for_user", False),
                hidden=att.get("hidden_for_user", False),
                page_name=label,
                page_id=pid,
                source="page",
                course_id=course_id,
            ))

    def add_module_item_to_tree(self, tree: CourseTree, course_id: int, item_id: int) -> bool:
        """Resuelve un item de módulo (URL /courses/:id/modules/items/:item_id)
        y agrega al árbol los archivos alcanzables según su tipo."""
        item = self.get_module_item(course_id, item_id)
        if not item:
            return False

        item_type = item.get("type", "")
        module_id = item.get("module_id")
        module_name = item.get("module_name")
        if module_id and not module_name:
            module_name = f"{_('Modulo')} {module_id}"
        if not module_name and module_id:
            try:
                for m in self.get_modules(course_id):
                    if str(m.get("id")) == str(module_id):
                        module_name = m.get("name")
                        break
            except (CanvasAPIError, requests.HTTPError):
                pass

        if item_type == "File":
            fid = item.get("content_id")
            if not fid:
                return False
            if self.ensure_file_in_tree(tree, course_id, fid):
                return True
            # Sin metadatos por API: aun así se lista con los datos del item.
            content = item.get("content_details", {})
            tree.add_file(CanvasFile(
                id=fid,
                folder_id=None,
                display_name=(content.get("display_name") or item.get("title") or _("archivo")),
                module_name=module_name,
                module_id=module_id,
                size=content.get("size") or item.get("size"),
                url=content.get("url"),
                locked=content.get("locked_for_user", False),
                hidden=content.get("hidden_for_user", False),
                source="module",
                course_id=course_id,
            ))
            tree.build_hierarchy()
            return True

        if item_type == "Page":
            self.resolve_page_item(tree, course_id, item, module_name, module_id)
            return True

        if item_type in ("Assignment", "Discussion", "Quiz"):
            self._resolve_content_item(tree, course_id, item, item_type, module_name)
            return True

        # ExternalUrl / ExternalTool / SubHeader: sin archivos alojados en Canvas.
        return False

    def _get_next_link(self, response: requests.Response) -> Optional[str]:
        link = response.headers.get("Link", "")
        for part in link.split(","):
            if 'rel="next"' in part:
                return part.split(";")[0].strip().strip("<>")
        return None

    def fetch_course_tree(self, course_id: int) -> CourseTree:
        try:
            cdata = self.get_course(course_id)
            course = CanvasCourse(id=course_id, name=cdata.get("name") or f"{_('Curso')} {course_id}")
        except (CanvasAPIError, requests.HTTPError):
            course = CanvasCourse(id=course_id, name=f"{_('Curso')}_{course_id}")

        tree = CourseTree(course)

        try:
            for module in self.get_modules(course_id):
                mname = module.get("name", f"{_('Modulo')} {module.get('id')}")
                mid = module.get("id")
                for item in module.get("items", []):
                    if item.get("type") == "File":
                        content = item.get("content_details", {})
                        fid = item.get("content_id")
                        if not fid: continue
                        # El title del item es la etiqueta del módulo y puede
                        # diferir del nombre real del archivo (p. ej. si el
                        # archivo fue reemplazado); metadata pone display_name.
                        tree.add_file(CanvasFile(
                            id=fid,
                            folder_id=None,
                            display_name=(content.get("display_name") or item.get("title") or _("archivo")),
                            module_name=mname,
                            module_id=mid,
                            size=content.get("size"),
                            url=content.get("url"),
                            locked=content.get("locked_for_user", False),
                            hidden=content.get("hidden_for_user", False),
                            source="module",
                            course_id=course_id,
                        ))
                    elif item.get("type") == "Page":
                        # Páginas de módulo: sus archivos no siempre figuran en
                        # el índice global /pages, así que se resuelven por item.
                        self.resolve_page_item(tree, course_id, item, mname, mid)
        except (CanvasAPIError, requests.HTTPError) as e:
            if not _is_http_forbidden(e): raise

        try:
            for f in self.get_folders(course_id):
                tree.add_folder(CanvasFolder(
                    id=f["id"],
                    parent_folder_id=f.get("parent_folder_id"),
                    name=f["name"],
                    full_name=f["full_name"],
                    is_root=(f.get("parent_folder_id") is None)
                ))
        except (CanvasAPIError, requests.HTTPError) as e:
            if not _is_http_forbidden(e): raise

        try:
            for f in self.get_files(course_id):
                fid = f.get("id")
                if not fid: continue
                folder_id = f.get("folder_id")
                api_name = (f.get("display_name") or f.get("filename") or "").strip()
                existing = tree.files.get(fid)
                if existing:
                    if existing.folder_id is None and folder_id is not None:
                        existing.folder_id = folder_id
                    if not existing.size and f.get("size"):
                        existing.size = f.get("size")
                    if existing.source == "none":
                        existing.source = "folder"
                    if api_name:
                        existing.display_name = api_name
                    # El índice de archivos trae el URL firmado real; aplicarlo
                    # a archivos de módulo que solo tenían el endpoint de metadata.
                    if not existing.url and f.get("url"):
                        existing.url = f.get("url")
                else:
                    tree.add_file(CanvasFile(
                        id=fid,
                        folder_id=folder_id,
                        display_name=api_name or _("archivo"),
                        module_name=None,
                        size=f.get("size"),
                        url=f.get("url"),
                        locked=f.get("locked_for_user", False),
                        hidden=f.get("hidden_for_user", False),
                        source="folder",
                        course_id=course_id,
                    ))
        except (CanvasAPIError, requests.HTTPError) as e:
            if not _is_http_forbidden(e): raise

        try:
            self._extract_rich_content_files(tree, course_id)
        except (CanvasAPIError, requests.HTTPError) as e:
            if not _is_http_forbidden(e): raise

        tree.build_hierarchy()
        return tree


def build_rich_tree(course_tree: CourseTree) -> Tuple[Tree, Dict[int, int]]:
    """Builds a rich Tree and returns a mapping from index -> file_id.

    Siempre renderiza todas las secciones: módulos, páginas, carpetas y
    archivos sueltos, sin ocultar unas por la presencia de otras.
    """
    root_node = Tree(f"[primary][{_('Curso')}] {course_tree.course.name}[/]")
    counter = [0]
    index_map: Dict[int, int] = {}
    rendered: set = set()

    all_files = list(course_tree.files.values())

    def _add_file(node: Tree, file: CanvasFile):
        counter[0] += 1
        idx = counter[0]
        index_map[idx] = file.id
        rendered.add(file.id)
        size_display = ""
        if file.source != "module":
            size_str = human_readable_size(file.size)
            size_display = f" [muted]({size_str})[/]"
        flags = ""
        if file.locked: flags = f" [secondary][{_('Bloqueado')}][/]"
        elif file.hidden: flags = f" [secondary][{_('Oculto')}][/]"
        node.add(f"[{idx}] [primary]{file.display_name}[/]{size_display}{flags}")

    def _populate_folder(fid: int, node: Tree):
        subids = course_tree.subfolders_map.get(fid, [])
        subs = [course_tree.folders[sid] for sid in subids if sid in course_tree.folders]
        subs.sort(key=lambda x: x.name.lower())
        for s in subs:
            fnode = node.add(f"[module][{_('Carpeta')}] {s.name}[/]")
            _populate_folder(s.id, fnode)

        fs = [f for f in course_tree.folder_files_map.get(fid, []) if f.id not in rendered]
        fs.sort(key=lambda x: x.display_name.lower())
        for f in fs:
            _add_file(node, f)

    module_files = [f for f in all_files if f.source == "module"]
    page_files = [f for f in all_files if f.source == "page"]

    if module_files:
        mdict = defaultdict(list)
        for f in module_files: mdict[f.module_name].append(f)
        for mname, fs in mdict.items():
            mnode = root_node.add(f"[module][{_('Modulo')}] {mname}[/]")
            fs.sort(key=lambda x: x.display_name.lower())
            for f in fs:
                if f.id not in rendered:
                    _add_file(mnode, f)

    if page_files:
        pages_node = root_node.add(f"[module][{_('Páginas')}][/]")
        pdict = defaultdict(list)
        for f in page_files: pdict[f.page_name].append(f)
        for pname, fs in pdict.items():
            pnode = pages_node.add(f"[module]{pname}[/]")
            fs.sort(key=lambda x: x.display_name.lower())
            for f in fs:
                if f.id not in rendered:
                    _add_file(pnode, f)

    has_folder_content = any(
        f.folder_id is not None and f.id not in rendered
        for f in all_files
    )
    if course_tree.folders and has_folder_content:
        if course_tree.root_folder_id is not None:
            _populate_folder(course_tree.root_folder_id, root_node)
        else:
            for fid, f in course_tree.folders.items():
                if f.parent_folder_id is None:
                    fnode = root_node.add(f"[module][{_('Carpeta')}] {f.name}[/]")
                    _populate_folder(fid, fnode)

    flat = [f for f in all_files if f.id not in rendered]
    flat.sort(key=lambda x: x.display_name.lower())
    for f in flat:
        _add_file(root_node, f)

    return root_node, index_map
