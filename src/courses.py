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
        
        if file.module_name:
            module_folder = clean_name(file.module_name)
            return base_dir / course_folder / module_folder / file_name
            
        if file.folder_id and self.folders:
            path_parts = []
            current_folder_id = file.folder_id
            while current_folder_id:
                folder = self.folders.get(current_folder_id)
                if not folder:
                    break
                path_parts.insert(0, clean_name(folder.name))
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
    if isinstance(e, CanvasAPIError):
        return e.status_code in (401, 403)
    if isinstance(e, requests.HTTPError):
        resp = getattr(e, "response", None)
        if resp is not None:
            return resp.status_code in (401, 403)
    return False

class CanvasAPIClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

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
                raise CanvasAuthError("Token de acceso invalido o expirado.", status_code=401)
            elif response.status_code == 404:
                raise CourseNotFoundError("El curso no fue encontrado.", status_code=404)
            elif response.status_code in (403, 429):
                err_msg = response.text.lower()
                if "rate limit" in err_msg or response.status_code == 429:
                    time.sleep(5.0)
                    response = self.session.request(method, url, **kwargs)
                    if response.status_code == 200:
                        return response
                    raise RateLimitError("Limite de solicitudes alcanzado.", status_code=response.status_code)
                raise CanvasAPIError(f"Acceso denegado ({response.status_code}): {response.text}", status_code=response.status_code)
            else:
                raise CanvasAPIError(f"Error HTTP {response.status_code}", status_code=response.status_code)

        except requests.exceptions.ConnectionError as e:
            raise CanvasConnectionError(f"No se pudo establecer conexion: {e}")
        except requests.RequestException as e:
            if isinstance(e, CanvasAPIError):
                raise
            raise CanvasAPIError(f"Error de red inesperado: {e}")

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

    def _get_next_link(self, response: requests.Response) -> Optional[str]:
        link = response.headers.get("Link", "")
        for part in link.split(","):
            if 'rel="next"' in part:
                return part.split(";")[0].strip().strip("<>")
        return None

    def fetch_course_tree(self, course_id: int) -> CourseTree:
        try:
            cdata = self.get_course(course_id)
            course = CanvasCourse(id=course_id, name=cdata.get("name") or f"Curso {course_id}")
        except (CanvasAPIError, requests.HTTPError):
            course = CanvasCourse(id=course_id, name=f"Curso_{course_id}")

        tree = CourseTree(course)

        try:
            for module in self.get_modules(course_id):
                mname = module.get("name", f"Modulo {module.get('id')}")
                for item in module.get("items", []):
                    if item.get("type") != "File":
                        continue
                    content = item.get("content_details", {})
                    fid = item.get("content_id")
                    if not fid: continue
                    tree.add_file(CanvasFile(
                        id=fid,
                        folder_id=None,
                        display_name=item.get("title") or "archivo",
                        module_name=mname,
                        size=content.get("size"),
                        url=content.get("url") or item.get("url"),
                        locked=content.get("locked_for_user", False),
                        hidden=content.get("hidden_for_user", False),
                    ))
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
                existing = tree.files.get(fid)
                if existing:
                    if existing.folder_id is None and folder_id is not None:
                        existing.folder_id = folder_id
                    if not existing.size and f.get("size"):
                        existing.size = f.get("size")
                else:
                    tree.add_file(CanvasFile(
                        id=fid,
                        folder_id=folder_id,
                        display_name=f.get("display_name") or "archivo",
                        module_name=None,
                        size=f.get("size"),
                        url=f.get("url"),
                        locked=f.get("locked_for_user", False),
                        hidden=f.get("hidden_for_user", False)
                    ))
        except (CanvasAPIError, requests.HTTPError) as e:
            if not _is_http_forbidden(e): raise

        tree.build_hierarchy()
        return tree


def build_rich_tree(course_tree: CourseTree) -> Tuple[Tree, Dict[int, int]]:
    """Builds a rich Tree and returns a mapping from index -> file_id."""
    root_node = Tree(f"[primary][Curso] {course_tree.course.name}[/]")
    counter = [0]
    index_map: Dict[int, int] = {}
    
    all_files = list(course_tree.files.values())
    module_files = [f for f in all_files if f.module_name is not None]
    
    def _add_file(node: Tree, file: CanvasFile):
        counter[0] += 1
        idx = counter[0]
        index_map[idx] = file.id
        size_str = human_readable_size(file.size)
        flags = ""
        if file.locked: flags = " [secondary][Bloqueado][/]"
        elif file.hidden: flags = " [secondary][Oculto][/]"
        node.add(f"[{idx}] [primary]{file.display_name}[/] [muted]({size_str})[/]{flags}")

    def _populate_folder(fid: int, node: Tree):
        subids = course_tree.subfolders_map.get(fid, [])
        subs = [course_tree.folders[sid] for sid in subids if sid in course_tree.folders]
        subs.sort(key=lambda x: x.name.lower())
        for s in subs:
            fnode = node.add(f"[primary][Carpeta] {s.name}[/]")
            _populate_folder(s.id, fnode)
            
        fs = course_tree.folder_files_map.get(fid, [])
        fs.sort(key=lambda x: x.display_name.lower())
        for f in fs:
            _add_file(node, f)

    if module_files:
        mdict = defaultdict(list)
        for f in module_files: mdict[f.module_name].append(f)
        for mname, fs in mdict.items():
            mnode = root_node.add(f"[module][Modulo] {mname}[/]")
            fs.sort(key=lambda x: x.display_name.lower())
            for f in fs: _add_file(mnode, f)
            
    elif course_tree.folders:
        if course_tree.root_folder_id is not None:
            _populate_folder(course_tree.root_folder_id, root_node)
        else:
            for fid, f in course_tree.folders.items():
                if f.parent_folder_id is None:
                    fnode = root_node.add(f"[primary][Carpeta] {f.name}[/]")
                    _populate_folder(fid, fnode)
                    
    else:
        flat = [f for f in all_files if f.module_name is None]
        flat.sort(key=lambda x: x.display_name.lower())
        for f in flat: _add_file(root_node, f)

    return root_node, index_map
