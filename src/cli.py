import os
import sys
from pathlib import Path
from typing import Dict, Optional, List, Tuple

from rich.prompt import Confirm, Prompt
from rich.tree import Tree
from src.theme import console

from src.core import Settings, extract_course_id, human_readable_size
from src.courses import CanvasAPIClient, CourseTree, CanvasFile, build_rich_tree
from src.downloader import DownloaderService, DownloadJob

def run_config_wizard() -> Settings:
    console.print("\n[secondary]─[/] [primary]CONFIGURACIÓN DE DOWNVAS[/] [secondary]──────────────────────[/]")
    console.print("Por favor, configure los parámetros de conexión de Canvas LMS.\n")
    
    settings = Settings.load()
    current_url = settings.canvas_url or "https://canvas.instructure.com"
    canvas_url = Prompt.ask("URL de Canvas LMS", default=current_url).strip()
    
    current_token = settings.api_token
    token_help = " (presione Enter para mantener el token actual)" if current_token else ""
    api_token = Prompt.ask(f"Token de acceso de Canvas{token_help}", default=current_token).strip()
    
    current_dir = str(settings.download_dir)
    download_dir = Prompt.ask("Carpeta de descarga local", default=current_dir).strip()
    
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
        update_or_add(env_lines, "CANVAS_DOWNLOAD_DIR", download_dir)
        
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        console.print("[success]Configuracion guardada en .env[/]\n")
        
        os.environ["CANVAS_URL"] = canvas_url
        os.environ["CANVAS_TOKEN"] = api_token
        os.environ["CANVAS_DOWNLOAD_DIR"] = download_dir
        return Settings.load()
        
    except Exception as e:
        console.print(f"[error]Error guardando configuración: {e}[/]\n")
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
        console.print(f"\n[secondary]Multiples archivos coinciden con '{query}':[/]")
        for idx, file in enumerate(matching, start=1):
            size_str = human_readable_size(file.size)
            console.print(f"  {idx}. {file.display_name} [muted]({size_str})[/]")
            
        choice = Prompt.ask("\nSeleccione el numero del archivo (Enter para cancelar)", default="").strip()
        if choice.isdigit():
            c_idx = int(choice) - 1
            if 0 <= c_idx < len(matching):
                return matching[c_idx]
    return None

def handle_view_tree(rich_tree: Tree):
    console.print(rich_tree)

def handle_download_single(course_tree: CourseTree, settings: Settings, downloader: DownloaderService, index_map: Dict[int, int]):
    query = Prompt.ask("\nIngrese el indice, nombre o ruta del archivo").strip()
    file = resolve_file(course_tree, query, index_map)
    if file:
        dest = course_tree.get_file_download_path(file.id, settings.download_dir)
        downloader.download_jobs([DownloadJob(file.url, dest, file.size, file.display_name, file.id, file.module_name is not None)])
    else:
        console.print("[error]Archivo no encontrado.[/]")

def handle_download_multi(course_tree: CourseTree, settings: Settings, downloader: DownloaderService, index_map: Dict[int, int]):
    queue: List[CanvasFile] = []
    console.print("Agregue archivos. Escriba 'finalizar' para terminar.")
    while True:
        q = Prompt.ask("Archivo").strip()
        if not q or q.lower() == "finalizar": break
        file = resolve_file(course_tree, q, index_map)
        if file:
            queue.append(file)
            console.print(f"[success]Agregado: {file.display_name}[/]")
        else:
            console.print("[error]No encontrado.[/]")
    if queue and Confirm.ask(f"[primary]Confirmar descarga de {len(queue)} archivos?[/]", default=True):
        jobs = [DownloadJob(f.url, course_tree.get_file_download_path(f.id, settings.download_dir), f.size, f.display_name, f.id, f.module_name is not None) for f in queue]
        downloader.download_jobs(jobs)

def handle_download_by_ext(course_tree: CourseTree, settings: Settings, downloader: DownloaderService):
    ext = Prompt.ask("\nExtension (ej: .pdf)").strip()
    if ext:
        fs = course_tree.get_files_by_extension(ext)
        if fs and Confirm.ask(f"[primary]Descargar {len(fs)} archivos?[/]", default=True):
            jobs = [DownloadJob(f.url, course_tree.get_file_download_path(f.id, settings.download_dir), f.size, f.display_name, f.id, f.module_name is not None) for f in fs]
            downloader.download_jobs(jobs)
        elif not fs:
            console.print("[secondary]No se encontraron archivos.[/]")

def handle_download_all(course_tree: CourseTree, settings: Settings, downloader: DownloaderService):
    fs = course_tree.get_all_files()
    if fs and Confirm.ask(f"[primary]Descargar todo ({len(fs)} archivos)?[/]", default=True):
        jobs = [DownloadJob(f.url, course_tree.get_file_download_path(f.id, settings.download_dir), f.size, f.display_name, f.id, f.module_name is not None) for f in fs]
        downloader.download_jobs(jobs)

def handle_refresh(course_id: int, api_client: CanvasAPIClient) -> Tuple[CourseTree, Tree, Dict[int, int]]:
    with console.status("[success]Actualizando...[/]"):
        course_tree = api_client.fetch_course_tree(course_id)
        rich_tree, index_map = build_rich_tree(course_tree)
    console.print("[success]Actualizado.[/]")
    return course_tree, rich_tree, index_map

def handle_change_course(api_client: CanvasAPIClient) -> Tuple[Optional[int], Optional[CourseTree], Optional[Tree], Dict[int, int]]:
    cid_str = Prompt.ask("\nID del nuevo curso").strip()
    cid = extract_course_id(cid_str)
    if cid:
        try:
            with console.status("[success]Validando curso...[/]"):
                cname = api_client.fetch_course_name(cid)
            with console.status(f"[success]Cargando datos del curso '{cname}'...[/]"):
                new_tree = api_client.fetch_course_tree(cid)
                new_rich_tree, new_map = build_rich_tree(new_tree)
            console.print(f"[success]Cambiado a: {new_tree.course.name}[/]")
            return cid, new_tree, new_rich_tree, new_map
        except Exception as e:
            console.print(f"[error]Error: {e}[/]")
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
        console.print("[secondary]No se encontraron secciones en el curso.[/]")
        return
        
    section_names = list(sections.keys())
    console.print("\n[primary]Secciones disponibles:[/]")
    for idx, name in enumerate(section_names, start=1):
        console.print(f"  {idx}. {name} [muted]({len(sections[name])} archivos)[/]")
        
    choice = Prompt.ask("\nSeleccione el numero de la seccion (Enter para cancelar)").strip()
    if not choice:
        return
        
    if choice.isdigit():
        c_idx = int(choice) - 1
        if 0 <= c_idx < len(section_names):
            selected_name = section_names[c_idx]
            files_to_download = sections[selected_name]
            
            if Confirm.ask(f"[primary]Descargar {len(files_to_download)} archivos de la seccion '{selected_name}'?[/]", default=True):
                jobs = [DownloadJob(f.url, course_tree.get_file_download_path(f.id, settings.download_dir), f.size, f.display_name, f.id, f.module_name is not None) for f in files_to_download]
                downloader.download_jobs(jobs)
        else:
            console.print("[error]Opcion invalida.[/]")
    else:
        console.print("[error]Entrada invalida.[/]")
