import os
import sys
from pathlib import Path
from string import Template
from typing import Dict, Optional, List, Tuple

from rich.prompt import Confirm, Prompt
from rich.tree import Tree
from src.theme import console

from src.core import Settings, extract_course_id, human_readable_size
from src.courses import CanvasAPIClient, CourseTree, CanvasFile, build_rich_tree
from src.downloader import DownloaderService, DownloadJob
from src.i18n import _

def run_config_wizard() -> Settings:
    console.print(f"\n[secondary]─[/] [primary]{_('CONFIGURACIÓN DE DOWNVAS')}[/] [secondary]──────────────────────[/]")
    console.print(f"{_('Por favor, configure los parámetros de conexión de Canvas LMS.')}\n")
    
    settings = Settings.load()
    current_url = settings.canvas_url or "https://canvas.instructure.com"
    while True:
        canvas_url = Prompt.ask(_("URL de Canvas LMS"), default=current_url).strip()
        if not canvas_url.startswith(("http://", "https://")):
            console.print(f"[error]{_('La URL de Canvas debe comenzar con http:// o https://')}[/]")
        else:
            break
    
    current_token = settings.api_token
    token_help = _(" (presione Enter para mantener el token actual)") if current_token else ""
    while True:
        api_token = Prompt.ask(f"{_('Token de acceso de Canvas')}{token_help}", default=current_token).strip()
        if not api_token:
            console.print(f"[error]{_('El token de acceso no puede estar vacio.')}[/]")
        else:
            break
    
    current_locale = settings.locale
    locale_prompt = f"{_('Idioma de la interfaz')} [muted]({_('Opciones validas')}: en, es)[/]"
    new_locale = Prompt.ask(locale_prompt, default=current_locale).strip()
    
    lang = new_locale.split("_")[0].lower()
    from src.core import _DEFAULT_FOLDER
    if os.getenv("CANVAS_DOWNLOAD_DIR"):
        default_dir_str = str(settings.download_dir)
    else:
        default_dir_str = str(Path.cwd() / _DEFAULT_FOLDER.get(lang, "Descargas"))

    download_dir = Prompt.ask(_("Carpeta de descarga local"), default=default_dir_str).strip()
    
    env_path = Path(".env")
    try:
        env_lines = []
        if env_path.exists():
            env_lines = env_path.read_text(encoding="utf-8").splitlines()
            
        def update_or_add(lines, key, val):
            found = False
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={val}"
                    found = True
                    break
            if not found:
                lines.append(f"{key}={val}")
                
        update_or_add(env_lines, "CANVAS_URL", canvas_url)
        update_or_add(env_lines, "CANVAS_TOKEN", api_token)
        update_or_add(env_lines, "CANVAS_LOCALE", new_locale)
        update_or_add(env_lines, "CANVAS_DOWNLOAD_DIR", download_dir)
        
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        console.print(f"[success]{_('Configuracion guardada en .env')}[/]\n")
        
        os.environ["CANVAS_URL"] = canvas_url
        os.environ["CANVAS_TOKEN"] = api_token
        os.environ["CANVAS_LOCALE"] = new_locale
        os.environ["CANVAS_DOWNLOAD_DIR"] = download_dir
        return Settings.load()
        
    except Exception as e:
        console.print(f"[error]{_('Error guardando configuración')}: {e}[/]\n")
        return settings

def resolve_file(tree: CourseTree, query: str, index_map: Dict[int, int]) -> Optional[CanvasFile]:
    query = query.strip()
    if not query:
        return None
        
    if query.isdigit():
        idx = int(query)
        file_id = index_map.get(idx)
        if file_id and file_id in tree.files:
            return tree.files[file_id]
            
    file_by_path = tree.find_file_by_path(query)
    if file_by_path:
        return file_by_path
        
    matching = tree.find_file_by_name(query)
    if not matching:
        return None
    elif len(matching) == 1:
        return matching[0]
    else:
        console.print(f"\n[secondary]{_('Multiples archivos coinciden con')} '{query}':[/]")
        for idx, file in enumerate(matching, start=1):
            size_str = human_readable_size(file.size)
            console.print(f"  {idx}. {file.display_name} [muted]({size_str})[/]")
            
        choice = Prompt.ask(f"\n{_('Seleccione el numero del archivo (Enter para cancelar)')}", default="").strip()
        if choice.isdigit():
            c_idx = int(choice) - 1
            if 0 <= c_idx < len(matching):
                return matching[c_idx]
    return None

def handle_view_tree(rich_tree: Tree):
    console.print(rich_tree)

def handle_download_single(course_tree: CourseTree, settings: Settings, downloader: DownloaderService, index_map: Dict[int, int]):
    query = Prompt.ask(f"\n{_('Ingrese el indice, nombre o ruta del archivo')}").strip()
    file = resolve_file(course_tree, query, index_map)
    if file:
        dest = course_tree.get_file_download_path(file.id, settings.download_dir)
        downloader.download_jobs([DownloadJob(file.url, dest, file.size, file.display_name, file.id, file.module_name is not None)])
    else:
        console.print(f"[error]{_('Archivo no encontrado.')}[/]")

def handle_download_multi(course_tree: CourseTree, settings: Settings, downloader: DownloaderService, index_map: Dict[int, int]):
    queue: List[CanvasFile] = []
    # Sentinel "finalizar" / "finish" — se compara contra ambas formas
    console.print(Template(_("Agregue archivos. Escriba 'finalizar' para terminar.")).safe_substitute())
    while True:
        q = Prompt.ask(_("Archivo")).strip()
        if not q or q.lower() in ("finalizar", "finish"):
            break
        file = resolve_file(course_tree, q, index_map)
        if file:
            queue.append(file)
            console.print(f"[success]{_('Agregado')}: {file.display_name}[/]")
        else:
            console.print(f"[error]{_('No encontrado.')}[/]")
    if queue and Confirm.ask(
        f"[primary]{Template(_('Confirmar descarga de $n archivos?')).safe_substitute(n=len(queue))}[/]",
        default=True
    ):
        jobs = [DownloadJob(f.url, course_tree.get_file_download_path(f.id, settings.download_dir), f.size, f.display_name, f.id, f.module_name is not None) for f in queue]
        downloader.download_jobs(jobs)

def handle_download_by_ext(course_tree: CourseTree, settings: Settings, downloader: DownloaderService):
    ext = Prompt.ask(f"\n{_('Extension (ej: .pdf)')}").strip()
    if ext:
        fs = course_tree.get_files_by_extension(ext)
        if fs and Confirm.ask(
            f"[primary]{Template(_('Descargar $n archivos?')).safe_substitute(n=len(fs))}[/]",
            default=True
        ):
            jobs = [DownloadJob(f.url, course_tree.get_file_download_path(f.id, settings.download_dir), f.size, f.display_name, f.id, f.module_name is not None) for f in fs]
            downloader.download_jobs(jobs)
        elif not fs:
            console.print(f"[secondary]{_('No se encontraron archivos.')}[/]")

def handle_download_all(course_tree: CourseTree, settings: Settings, downloader: DownloaderService):
    fs = course_tree.get_all_files()
    if fs and Confirm.ask(
        f"[primary]{Template(_('Descargar todo ($n archivos)?')).safe_substitute(n=len(fs))}[/]",
        default=True
    ):
        jobs = [DownloadJob(f.url, course_tree.get_file_download_path(f.id, settings.download_dir), f.size, f.display_name, f.id, f.module_name is not None) for f in fs]
        downloader.download_jobs(jobs)

def handle_refresh(course_id: int, api_client: CanvasAPIClient) -> Tuple[CourseTree, Tree, Dict[int, int]]:
    with console.status(f"[success]{_('Actualizando...')}[/]"):
        course_tree = api_client.fetch_course_tree(course_id)
        rich_tree, index_map = build_rich_tree(course_tree)
    console.print(f"[success]{_('Actualizado.')}[/]")
    return course_tree, rich_tree, index_map

def handle_change_course(api_client: CanvasAPIClient) -> Tuple[Optional[int], Optional[CourseTree], Optional[Tree], Dict[int, int]]:
    cid_str = Prompt.ask(f"\n{_('ID del nuevo curso')}").strip()
    cid = extract_course_id(cid_str)
    if cid:
        try:
            with console.status(f"[success]{_('Validando curso...')}[/]"):
                cname = api_client.fetch_course_name(cid)
            with console.status(f"[success]{_('Actualizando...')}[/]"):
                new_tree = api_client.fetch_course_tree(cid)
                new_rich_tree, new_map = build_rich_tree(new_tree)
            console.print(f"[success]{_('Cambiado a')}: {new_tree.course.name}[/]")
            return cid, new_tree, new_rich_tree, new_map
        except Exception as e:
            console.print(f"[error]{_('Error')}: {e}[/]")
    return None, None, None, {}

def handle_download_by_section(course_tree: CourseTree, settings: Settings, downloader: DownloaderService):
    sections: Dict[str, List[CanvasFile]] = {}
    
    for file in course_tree.files.values():
        if file.module_name:
            sections.setdefault(file.module_name, []).append(file)
            
    if not sections:
        for folder in course_tree.folders.values():
            folder_files = course_tree.folder_files_map.get(folder.id, [])
            if folder_files:
                sections[folder.name] = folder_files
                
    if not sections:
        console.print(f"[secondary]{_('No se encontraron secciones en el curso.')}[/]")
        return
        
    section_names = list(sections.keys())
    console.print(f"\n[primary]{_('Secciones disponibles:')}[/]")
    for idx, name in enumerate(section_names, start=1):
        console.print(f"  {idx}. {name} [muted]({len(sections[name])} archivos)[/]")
        
    choice = Prompt.ask(f"\n{_('Seleccione el numero de la seccion (Enter para cancelar)')}").strip()
    if not choice:
        return
        
    if choice.isdigit():
        c_idx = int(choice) - 1
        if 0 <= c_idx < len(section_names):
            selected_name = section_names[c_idx]
            files_to_download = sections[selected_name]
            
            msg = Template(_("Descargar $n archivos de la seccion '$s'?")).safe_substitute(n=len(files_to_download), s=selected_name)
            if Confirm.ask(
                f"[primary]{msg}[/]",
                default=True
            ):
                jobs = [DownloadJob(f.url, course_tree.get_file_download_path(f.id, settings.download_dir), f.size, f.display_name, f.id, f.module_name is not None) for f in files_to_download]
                downloader.download_jobs(jobs)
        else:
            console.print(f"[error]{_('Opcion invalida.')}[/]")
    else:
        console.print(f"[error]{_('Entrada invalida.')}[/]")
