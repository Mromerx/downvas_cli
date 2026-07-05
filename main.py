#!/usr/bin/env python3
"""
DownVas - Canvas Downloader CLI Entry Point.
Orquestador principal que media entre los componentes de dominio.
"""

import sys
from typing import Dict, Optional, List

from rich.prompt import Confirm, Prompt
from src.theme import console

from src.core import (
    Settings,
    DownVasError,
    CanvasAuthError,
    CourseNotFoundError,
    ConnectionError as CanvasConnectionError,
    extract_course_id,
    extract_domain,
    human_readable_size
)
from src.courses import CanvasAPIClient, CourseTree, CanvasFile, build_rich_tree
from src.downloader import DownloaderService, DownloadJob


def run_config_wizard() -> Settings:
    """Configura interactivamente y carga Settings."""
    console.print("\n[primary]=== CONFIGURACIÓN DE DOWNVAS ===[/]")
    console.print("Por favor, configure los parámetros de conexión de Canvas LMS.\n")
    
    settings = Settings.load()
    current_url = settings.canvas_url or "https://canvas.instructure.com"
    canvas_url = Prompt.ask("URL de Canvas LMS", default=current_url).strip()
    
    current_token = settings.api_token
    token_help = " (presione Enter para mantener el token actual)" if current_token else ""
    api_token = Prompt.ask(f"Token de acceso de Canvas{token_help}", default=current_token).strip()
    
    current_dir = str(settings.download_dir)
    download_dir = Prompt.ask("Carpeta de descarga local", default=current_dir).strip()
    
    from pathlib import Path
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
        
        import os
        os.environ["CANVAS_URL"] = canvas_url
        os.environ["CANVAS_TOKEN"] = api_token
        os.environ["CANVAS_DOWNLOAD_DIR"] = download_dir
        return Settings.load()
        
    except Exception as e:
        console.print(f"[error]Error guardando configuración: {e}[/]\n")
        return settings

def resolve_file(tree: CourseTree, query: str, index_map: Dict[int, int]) -> Optional[CanvasFile]:
    """Busca un archivo en el árbol por índice o nombre."""
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


def main() -> None:
    settings = Settings.load()
    ascii_art = r"""[primary] ___               __   __       
|   \ _____ __ ___ \ \ / /_ _ ___
| |) / _ \ V  V / ' \ V / _` (_-<
|___/\___/\_/\_/|_||_\_/\__,_/__/[/]
"""
    console.print(ascii_art)
    console.print("DownVas - Canvas Downloader", style="secondary")    
    if not settings.is_configured:
        settings = run_config_wizard()
        
    api_client = CanvasAPIClient(settings.canvas_url, settings.api_token)
    downloader = DownloaderService(settings.canvas_url, settings.api_token)
    
    try:
        with console.status("[success]Verificando credenciales...[/]"):
            api_client.verify_authentication()
    except CanvasAuthError:
        console.print("[error]Token invalido o expirado.[/]")
        if Confirm.ask("[primary]Desea reconfigurar?[/]", default=True):
            settings = run_config_wizard()
            api_client = CanvasAPIClient(settings.canvas_url, settings.api_token)
            downloader = DownloaderService(settings.canvas_url, settings.api_token)
            api_client.verify_authentication()
        else:
            sys.exit(1)
            
    course_id: Optional[int] = None
    course_tree: Optional[CourseTree] = None
    index_map: Dict[int, int] = {}
    
    while course_tree is None:
        cid_str = Prompt.ask("\nIngrese el ID del curso o URL completa").strip()
        cid = extract_course_id(cid_str)
        if cid is None:
            console.print("[error]ID invalido.[/]")
            continue
            
        domain = extract_domain(cid_str)
        if domain and domain.rstrip("/") != settings.canvas_url.rstrip("/"):
            console.print(f"[secondary]El dominio ingresado ({domain}) no coincide con el configurado ({settings.canvas_url}).[/]")
            if Confirm.ask("[primary]Desea actualizar la URL?[/]", default=True):
                settings = run_config_wizard()
                api_client = CanvasAPIClient(settings.canvas_url, settings.api_token)
                downloader = DownloaderService(settings.canvas_url, settings.api_token)
                
        try:
            with console.status("[success]Validando curso...[/]"):
                cname = api_client.fetch_course_name(cid)
            with console.status(f"[success]Cargando estructura de '{cname}'...[/]"):
                course_tree = api_client.fetch_course_tree(cid)
                rich_tree, index_map = build_rich_tree(course_tree)
            course_id = cid
            console.print(f"[success]Curso cargado: {course_tree.course.name}[/]")
        except CourseNotFoundError:
            console.print("[error]Curso no encontrado o sin permisos.[/]")
        except Exception as e:
            console.print(f"[error]Error al cargar curso: {e}[/]")
            
    while True:
        console.print("[secondary]─[/] [primary]MENU[/] [secondary]─────────────────────────────────────────[/]")
        menu_options = [
            ("1",  "Ver listado del curso"),
            ("2",  "Descargar un archivo"),
            ("3",  "Descargar varios archivos"),
            ("4",  "Descargar archivos por extension (ej: .pdf)"),
            ("5",  "Descargar todos los archivos del curso"),
            ("6",  "Actualizar informacion del curso"),
            ("7",  "Cambiar de curso"),
            ("8",  "Cambiar URL de Canvas"),
            ("9",  "Cambiar token de acceso"),
            ("10", "Salir"),
        ]
        for num, desc in menu_options:
            console.print(f" [primary]\\[{num}][/] {desc}")
        console.print()
        while True:
            option = Prompt.ask("Opcion").strip()
            if option in [str(i) for i in range(1, 11)]:
                break
            console.print("[error]Opcion invalida.[/]")
        
        if option == "1":
            console.print(rich_tree)
            
        elif option == "2":
            query = Prompt.ask("\nIngrese el indice, nombre o ruta del archivo").strip()
            file = resolve_file(course_tree, query, index_map)
            if file:
                dest = course_tree.get_file_download_path(file.id, settings.download_dir)
                downloader.download_jobs([DownloadJob(file.url, dest, file.size, file.display_name, file.id)])
            else:
                console.print("[error]Archivo no encontrado.[/]")
                
        elif option == "3":
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
                jobs = [DownloadJob(f.url, course_tree.get_file_download_path(f.id, settings.download_dir), f.size, f.display_name, f.id) for f in queue]
                downloader.download_jobs(jobs)
                
        elif option == "4":
            ext = Prompt.ask("\nExtension (ej: .pdf)").strip()
            if ext:
                fs = course_tree.get_files_by_extension(ext)
                if fs and Confirm.ask(f"[primary]Descargar {len(fs)} archivos?[/]", default=True):
                    jobs = [DownloadJob(f.url, course_tree.get_file_download_path(f.id, settings.download_dir), f.size, f.display_name, f.id) for f in fs]
                    downloader.download_jobs(jobs)
                elif not fs:
                    console.print("[secondary]No se encontraron archivos.[/]")
                    
        elif option == "5":
            fs = course_tree.get_all_files()
            if fs and Confirm.ask(f"[primary]Descargar todo ({len(fs)} archivos)?[/]", default=True):
                jobs = [DownloadJob(f.url, course_tree.get_file_download_path(f.id, settings.download_dir), f.size, f.display_name, f.id) for f in fs]
                downloader.download_jobs(jobs)
                
        elif option == "6":
            with console.status("[success]Actualizando...[/]"):
                course_tree = api_client.fetch_course_tree(course_id)
                rich_tree, index_map = build_rich_tree(course_tree)
            console.print("[success]Actualizado.[/]")
            
        elif option == "7":
            cid_str = Prompt.ask("\nID del nuevo curso").strip()
            cid = extract_course_id(cid_str)
            if cid:
                try:
                    with console.status("[success]Validando curso...[/]"):
                        cname = api_client.fetch_course_name(cid)
                    with console.status(f"[success]Cargando estructura de '{cname}'...[/]"):
                        new_tree = api_client.fetch_course_tree(cid)
                        new_rich_tree, new_map = build_rich_tree(new_tree)
                    course_id, course_tree, rich_tree, index_map = cid, new_tree, new_rich_tree, new_map
                    console.print(f"[success]Cambiado a: {course_tree.course.name}[/]")
                except Exception as e:
                    console.print(f"[error]Error: {e}[/]")
                    
        elif option == "8":
            console.print(f"\nURL actual: [secondary]{settings.canvas_url}[/]")
            new_url = Prompt.ask("Nueva URL de Canvas (ej: https://canvas.instructure.com)").strip()
            if not new_url:
                console.print("[error]La URL no puede estar vacia. Operacion cancelada.[/]")
            else:
                try:
                    settings.update_url(new_url)
                    api_client = CanvasAPIClient(settings.canvas_url, settings.api_token)
                    downloader = DownloaderService(settings.canvas_url, settings.api_token)
                    console.print(f"[success]URL actualizada a: {settings.canvas_url}[/]")
                    console.print("[muted]Los servicios han sido reiniciados con la nueva URL.[/]")
                except Exception as e:
                    console.print(f"[error]Error al actualizar URL: {e}[/]")

        elif option == "9":
            console.print("\nToken actual: [muted](oculto por seguridad)[/]")
            new_token = Prompt.ask("Nuevo token de acceso de Canvas").strip()
            if not new_token:
                console.print("[error]El token no puede estar vacio. Operacion cancelada.[/]")
            else:
                try:
                    settings.update_token(new_token)
                    api_client = CanvasAPIClient(settings.canvas_url, settings.api_token)
                    downloader = DownloaderService(settings.canvas_url, settings.api_token)
                    console.print("[success]Token actualizado correctamente.[/]")
                    console.print("[muted]Los servicios han sido reiniciados con el nuevo token.[/]")
                except Exception as e:
                    console.print(f"[error]Error al actualizar token: {e}[/]")
                    
        elif option == "10":
            console.print("[success]Saliendo...[/]")
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[error]Interrumpido.[/]")
        sys.exit(0)
