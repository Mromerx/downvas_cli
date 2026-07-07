#!/usr/bin/env python3
import sys
from typing import Dict, Optional

from rich.prompt import Confirm, Prompt
from src.theme import console

from src.core import (
    Settings,
    CanvasAuthError,
    CourseNotFoundError,
    extract_course_id,
    extract_domain
)
from src.courses import CanvasAPIClient, CourseTree, build_rich_tree
from src.downloader import DownloaderService

from src.cli import (
    run_config_wizard,
    handle_view_tree,
    handle_download_single,
    handle_download_multi,
    handle_download_by_ext,
    handle_download_all,
    handle_refresh,
    handle_change_course,
    handle_download_by_section
)

def main() -> None:
    console.clear()
    settings = Settings.load()
    ascii_art = r"""[primary] ___               __   __       
|   \ _____ __ ___ \ \ / /_ _ ___
| |) / _ \ V  V / ' \ V / _` (_-<
|___/\___/\_/\_/|_||_\_/\__,_/__/[/]
"""
    console.print(ascii_art)
    console.print("   DownVas - Canvas Downloader", style="secondary")    
    if not settings.is_configured:
        settings = run_config_wizard()
        console.clear()
        
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
    rich_tree = None
    
    while course_tree is None:
        cid_str = Prompt.ask("\nIngrese el ID del curso o URL completa\n  o 'credenciales' para reconfigurar").strip()
        if cid_str.lower() in ("credenciales", "config", "0"):
            settings = run_config_wizard()
            api_client = CanvasAPIClient(settings.canvas_url, settings.api_token)
            downloader = DownloaderService(settings.canvas_url, settings.api_token)
            continue
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
            with console.status(f"[success]Cargando datos del curso '{cname}'...[/]"):
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
            ("2",  "Actualizar informacion del curso"),
            ("3",  "Descargar un archivo"),
            ("4",  "Descargar varios archivos"),
            ("5",  "Descargar archivos por extension (ej: .pdf)"),
            ("6",  "Descargar todos los archivos del curso"),
            ("7",  "Descargar por seccion"),
            ("8",  "Reasignar credenciales"),
            ("9",  "Cambiar de curso"),
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
            handle_view_tree(rich_tree)
        elif option == "2":
            course_tree, rich_tree, index_map = handle_refresh(course_id, api_client)
        elif option == "3":
            handle_download_single(course_tree, settings, downloader, index_map)
        elif option == "4":
            handle_download_multi(course_tree, settings, downloader, index_map)
        elif option == "5":
            handle_download_by_ext(course_tree, settings, downloader)
        elif option == "6":
            handle_download_all(course_tree, settings, downloader)
        elif option == "7":
            handle_download_by_section(course_tree, settings, downloader)
        elif option == "8":
            console.clear()
            settings = run_config_wizard()
            console.clear()
            api_client = CanvasAPIClient(settings.canvas_url, settings.api_token)
            downloader = DownloaderService(settings.canvas_url, settings.api_token)
        elif option == "9":
            new_cid, new_ctree, new_rtree, new_imap = handle_change_course(api_client)
            if new_cid is not None:
                course_id, course_tree, rich_tree, index_map = new_cid, new_ctree, new_rtree, new_imap
        elif option == "10":
            console.print("[success]Saliendo...[/]")
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[error]Interrumpido.[/]")
        sys.exit(0)
