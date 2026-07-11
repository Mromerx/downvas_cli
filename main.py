#!.venv/bin/python
import sys
from string import Template
from typing import Dict, Optional

from dotenv import load_dotenv

load_dotenv()

from rich.prompt import Confirm, Prompt
from src.theme import console

from src.core import (
    Settings,
    DownVasError,
    CanvasAPIError,
    CanvasAuthError,
    CourseNotFoundError,
    extract_course_id,
    extract_domain
)
from src.courses import CanvasAPIClient, CourseTree, build_rich_tree
from src.downloader import DownloaderService
from src.i18n import setup_i18n, _, get_sentinel

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

    # Inicializar i18n antes de cualquier output
    setup_i18n(settings.locale)

    ascii_art = r"""[primary] ___               __   __       
|   \ _____ __ ___ \ \ / /_ _ ___
| |) / _ \ V  V / ' \ V / _` (_-<
|___/\___/\_/\_/|_||_\_/\__,_/__/[/]
"""
    console.print(ascii_art)
    console.print(_("   DownVas - Canvas Downloader"), style="secondary")
    if not settings.is_configured:
        settings = run_config_wizard()
        setup_i18n(settings.locale)
        console.clear()
        
    api_client = CanvasAPIClient(settings.canvas_url, settings.api_token)
    downloader = DownloaderService(settings.canvas_url, settings.api_token)
    
    while True:
        try:
            with console.status(f"[success]{_('Verificando credenciales...')}[/]"):
                api_client.verify_authentication()
            break
        except DownVasError as e:
            if isinstance(e, CanvasAuthError):
                console.print(f"[error]{_('Token invalido o expirado.')}[/]")
            else:
                console.print(f"[error]{e}[/]")
            if not Confirm.ask(f"[primary]{_('Desea reconfigurar?')}[/]", default=True):
                sys.exit(1)
            settings = run_config_wizard()
            setup_i18n(settings.locale)
            api_client = CanvasAPIClient(settings.canvas_url, settings.api_token)
            downloader = DownloaderService(settings.canvas_url, settings.api_token)
            
    course_id: Optional[int] = None
    course_tree: Optional[CourseTree] = None
    index_map: Dict[int, int] = {}
    rich_tree = None
    
    while course_tree is None:
        lang = settings.locale.split("_")[0].lower()
        sentinel_hint = Template(_(
            "o '$s' para reconfigurar"
        )).safe_substitute(s=get_sentinel("credenciales", lang))
        cid_str = Prompt.ask(
            f"\n{_('Ingrese el ID del curso o URL completa')}\n  {sentinel_hint}"
        ).strip()
        if cid_str.lower() in (
            get_sentinel("credenciales", lang),
            get_sentinel("config", lang),
            "0",
        ):
            settings = run_config_wizard()
            setup_i18n(settings.locale)
            console.clear()
            api_client = CanvasAPIClient(settings.canvas_url, settings.api_token)
            downloader = DownloaderService(settings.canvas_url, settings.api_token)
            try:
                with console.status(f"[success]{_('Verificando credenciales...')}[/]"):
                    api_client.verify_authentication()
            except DownVasError as e:
                if isinstance(e, CanvasAuthError):
                    console.print(f"[error]{_('Token invalido o expirado.')}[/]")
                else:
                    console.print(f"[error]{e}[/]")
            continue
        cid = extract_course_id(cid_str)
        if cid is None:
            console.print(f"[error]{_('ID invalido.')}[/]")
            continue
            
        domain = extract_domain(cid_str)
        if domain and domain.rstrip("/") != settings.canvas_url.rstrip("/"):
            console.print(f"[secondary]{_('El dominio ingresado no coincide con el configurado.')}[/]")
            if Confirm.ask(f"[primary]{_('Desea actualizar la URL?')}[/]", default=True):
                settings = run_config_wizard()
                setup_i18n(settings.locale)
                api_client = CanvasAPIClient(settings.canvas_url, settings.api_token)
                downloader = DownloaderService(settings.canvas_url, settings.api_token)
                
        try:
            with console.status(f"[success]{_('Validando curso...')}[/]"):
                cname = api_client.fetch_course_name(cid)
            with console.status(f"[success]{Template(_('Actualizando...')).safe_substitute()}[/]"):
                course_tree = api_client.fetch_course_tree(cid)
                rich_tree, index_map = build_rich_tree(course_tree)
            course_id = cid
            console.print(f"[success]{_('Curso cargado')}: {course_tree.course.name}[/]")
        except CourseNotFoundError:
            console.print(f"[error]{_('Curso no encontrado o sin permisos.')}[/]")
        except Exception as e:
            console.print(f"[error]{_('Error al cargar curso')}: {e}[/]")
            
    while True:
        console.print(f"[secondary]─[/] [primary]{_('MENU')}[/] [secondary]─────────────────────────────────────────[/]")
        menu_options = [
            ("1",  _("Ver listado del curso")),
            ("2",  _("Actualizar informacion del curso")),
            ("3",  _("Descargar un archivo")),
            ("4",  _("Descargar varios archivos")),
            ("5",  _("Descargar archivos por extension (ej: .pdf)")),
            ("6",  _("Descargar todos los archivos del curso")),
            ("7",  _("Descargar por seccion")),
            ("8",  _("Reasignar credenciales")),
            ("9",  _("Cambiar de curso")),
            ("10", _("Salir")),
        ]
        for num, desc in menu_options:
            console.print(f" [primary]\\[{num}][/] {desc}")
        console.print()
        while True:
            option = Prompt.ask(_("Opcion")).strip()
            if option in [str(i) for i in range(1, 11)]:
                break
            console.print(f"[error]{_('Opcion invalida.')}[/]")
        
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
            setup_i18n(settings.locale)
            console.clear()
            api_client = CanvasAPIClient(settings.canvas_url, settings.api_token)
            downloader = DownloaderService(settings.canvas_url, settings.api_token)
            try:
                with console.status(f"[success]{_('Verificando credenciales...')}[/]"):
                    api_client.verify_authentication()
            except DownVasError as e:
                if isinstance(e, CanvasAuthError):
                    console.print(f"[error]{_('Token invalido o expirado.')}[/]")
                else:
                    console.print(f"[error]{e}[/]")
        elif option == "9":
            new_cid, new_ctree, new_rtree, new_imap = handle_change_course(api_client)
            if new_cid is not None:
                course_id, course_tree, rich_tree, index_map = new_cid, new_ctree, new_rtree, new_imap
        elif option == "10":
            console.print(f"[success]{_('Saliendo...')}[/]")
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print(f"\n[error]{_('Interrumpido.')}[/]")
        sys.exit(0)
