"""
Downloader module: File Writing (Data), Queue Management (Domain), and Progress Bars (Presentation).
"""
import os
import requests
from typing import List, Callable, Optional, Dict
from pathlib import Path
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

from src.theme import console
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
    TaskID
)

from src.core import CanvasAPIError

@dataclass
class DownloadJob:
    url: str
    destination: Path
    expected_size: Optional[int]
    display_name: str
    file_id: int

@dataclass
class DownloadSummary:
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    total_bytes_downloaded: int = 0
    total_duration: float = 0.0

class FileDownloader:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def download_file(self, job: DownloadJob, progress_callback: Callable[[int], None] = None) -> int:
        """Downloads a file in chunks, invoking progress_callback with bytes downloaded. Returns bytes downloaded."""
        if job.destination.exists():
            local_size = os.path.getsize(job.destination)
            if job.expected_size is None or local_size == job.expected_size:
                return 0

        job.destination.parent.mkdir(parents=True, exist_ok=True)
        bytes_dl = 0
        part_file = job.destination.with_name(job.destination.name + '.part')
        
        try:
            api_url = f"{self.base_url}/api/v1/files/{job.file_id}"
            meta_resp = self.session.get(api_url, timeout=10)
            meta_resp.raise_for_status()
            
            meta_json = meta_resp.json()
            download_url = meta_json.get("url")
            
            if not download_url:
                raise CanvasAPIError(f"No se encontro la URL de descarga para el archivo {job.display_name}")

            with requests.get(download_url, stream=True, allow_redirects=True, timeout=30) as r:
                r.raise_for_status()
                
                content_type = r.headers.get("Content-Type", "")
                if "application/json" in content_type and not job.display_name.lower().endswith(".json"):
                    raise CanvasAPIError("La descarga devolvio JSON inesperado en lugar de binario.")
                
                with open(part_file, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            bytes_dl += len(chunk)
                            if progress_callback:
                                progress_callback(len(chunk))
            
            if part_file.exists():
                part_file.replace(job.destination)
                
            return bytes_dl
        except Exception as e:
            if part_file.exists():
                try:
                    part_file.unlink()
                except OSError:
                    pass
            if job.destination.exists() and bytes_dl > 0:
                try:
                    job.destination.unlink()
                except OSError:
                    pass
            raise CanvasAPIError(f"Error descargando {job.display_name}: {e}")

class DownloaderService:
    def __init__(self, base_url: str, token: str):
        self.downloader = FileDownloader(base_url, token)

    def download_jobs(self, jobs: List[DownloadJob]) -> DownloadSummary:
        from rich.table import Table
        from rich.panel import Panel
        from src.core import human_readable_size
        import time

        summary = DownloadSummary()
        if not jobs:
            return summary

        progress = Progress(
            TextColumn("[primary]{task.description}", justify="right"),
            BarColumn(bar_width=40),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            DownloadColumn(),
            "•",
            TransferSpeedColumn(),
            "•",
            TimeRemainingColumn(),
            console=console,
        )

        start_time = time.time()
        skipped_jobs = []
        failed_jobs = []
        downloaded_jobs = []

        with progress:
            for job in jobs:
                if job.destination.exists():
                    local_size = os.path.getsize(job.destination)
                    if job.expected_size is None or local_size == job.expected_size:
                        progress.console.print(f"  [secondary][-][/] {job.display_name} [muted](Ya existe, omitido)[/]")
                        summary.skipped += 1
                        skipped_jobs.append(job)
                        continue

                task_id = progress.add_task(job.display_name, total=job.expected_size or 0)
                
                def update_progress(chunk_size: int):
                    progress.update(task_id, advance=chunk_size)

                try:
                    progress.start_task(task_id)
                    bytes_dl = self.downloader.download_file(job, progress_callback=update_progress)
                    progress.update(task_id, completed=job.expected_size or bytes_dl)
                    progress.console.print(f"  [success][OK][/] {job.display_name} [muted]({human_readable_size(bytes_dl)})[/]")
                    summary.successful += 1
                    summary.total_bytes_downloaded += bytes_dl
                    downloaded_jobs.append(job)
                except Exception as e:
                    err_msg = str(e)
                    progress.console.print(f"  [error][!][/] {job.display_name} [error][Fallido: {err_msg}][/]")
                    summary.failed += 1
                    summary.errors.append(err_msg)
                    failed_jobs.append((job, err_msg))
                finally:
                    progress.remove_task(task_id)

        summary.total_duration = max(0.1, time.time() - start_time)

        console.print("\n" + "=" * 52)
        console.print("[success]RESUMEN DE DESCARGA[/]")
        console.print("=" * 52)

        if failed_jobs or skipped_jobs:
            table = Table(title="Detalle de Operaciones", show_lines=True)
            table.add_column("Archivo", style="primary")
            table.add_column("Estado", justify="center")
            table.add_column("Detalle/Error", style="muted")
            
            for job in downloaded_jobs[:10]:
                table.add_row(job.display_name, "[success]Descargado[/]", "Completado con exito")
            if len(downloaded_jobs) > 10:
                table.add_row(f"... y {len(downloaded_jobs) - 10} archivos mas", "[success]Descargados[/]", "-")

            for job in skipped_jobs:
                table.add_row(job.display_name, "[secondary]Omitido[/]", "Archivo ya existente localmente")

            for job, err in failed_jobs:
                table.add_row(job.display_name, "[error]Fallido[/]", err)
                
            console.print(table)
            console.print()

        total_files = len(jobs)
        size_str = human_readable_size(summary.total_bytes_downloaded)
        speed_str = "0 B/s"
        if summary.total_duration > 0 and summary.total_bytes_downloaded > 0:
            speed_val = summary.total_bytes_downloaded / summary.total_duration
            speed_str = f"{human_readable_size(int(speed_val))}/s"
            
        mins = int(summary.total_duration // 60)
        secs = summary.total_duration % 60
        duration_str = f"{mins}m {secs:.1f}s" if mins > 0 else f"{secs:.1f}s"
        
        metrics_content = (
            f"- [bold]Archivos procesados:[/] {total_files}\n"
            f"  - [success]Descargados con exito:[/] {summary.successful}\n"
            f"  - [secondary]Omitidos (ya existentes):[/] {summary.skipped}\n"
            f"  - [error]Fallidos con error:[/] {summary.failed}\n"
            f"- [bold]Total descargado:[/] {size_str}\n"
            f"- [bold]Tiempo total:[/] {duration_str}\n"
            f"- [bold]Velocidad media:[/] {speed_str}"
        )
        
        console.print(Panel(metrics_content, title="[success]Métricas de Descarga[/]", expand=False, border_style="success"))
        console.print()

        return summary
