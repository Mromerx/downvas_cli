"""
Downloader module: File Writing (Data), Queue Management (Domain), and Progress Bars (Presentation).
"""
import os
import requests
from typing import List, Callable, Optional, Dict
from pathlib import Path
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from string import Template

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
from src.i18n import _

@dataclass
class DownloadJob:
    url: str
    destination: Path
    expected_size: Optional[int]
    display_name: str
    file_id: int
    from_module: bool = False

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
                raise CanvasAPIError(f"{_('No se encontro la URL de descarga para el archivo')} {job.display_name}")

            with requests.get(download_url, stream=True, allow_redirects=True, timeout=30) as r:
                r.raise_for_status()
                
                content_type = r.headers.get("Content-Type", "")
                if "application/json" in content_type and not job.display_name.lower().endswith(".json"):
                    raise CanvasAPIError(_("La descarga devolvio JSON inesperado en lugar de binario."))
                
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
            raise CanvasAPIError(f"{_('Error descargando')} {job.display_name}: {e}")

class DownloaderService:
    def __init__(self, base_url: str, token: str):
        self.downloader = FileDownloader(base_url, token)

    def download_jobs(self, jobs: List[DownloadJob]) -> DownloadSummary:
        from rich.table import Table
        from rich.panel import Panel
        from rich.progress import ProgressColumn
        from rich.text import Text
        from src.core import human_readable_size
        import time

        class CompletedSizeColumn(ProgressColumn):
            def render(self, task) -> Text:
                return Text(human_readable_size(task.completed), style="progress.download")

        summary = DownloadSummary()
        if not jobs:
            return summary

        from_modules = any(j.from_module for j in jobs)

        if from_modules:
            progress = Progress(
                TextColumn("[primary]{task.description}", justify="right"),
                BarColumn(bar_width=40),
                CompletedSizeColumn(),
                console=console,
            )
        else:
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
            from concurrent.futures import as_completed
            jobs_to_download = []
            
            for job in jobs:
                if job.destination.exists():
                    local_size = os.path.getsize(job.destination)
                    if job.expected_size is None or local_size == job.expected_size:
                        progress.console.print(f"  [secondary][-][/] {job.display_name} [muted]({_('Ya existe, omitido')})[/]")
                        summary.skipped += 1
                        skipped_jobs.append(job)
                        continue

                task_id = progress.add_task(job.display_name, total=job.expected_size or 0, start=False)
                jobs_to_download.append((job, task_id))

            def _worker(w_job, w_task_id):
                def update_progress(chunk_size: int):
                    progress.update(w_task_id, advance=chunk_size)

                progress.start_task(w_task_id)
                w_bytes = self.downloader.download_file(w_job, progress_callback=update_progress)
                progress.update(w_task_id, completed=w_job.expected_size or w_bytes)
                return w_bytes

            with ThreadPoolExecutor(max_workers=5) as pool:
                futures = {pool.submit(_worker, j, tid): (j, tid) for j, tid in jobs_to_download}
                for future in as_completed(futures):
                    j, tid = futures[future]
                    try:
                        bytes_dl = future.result()
                        progress.console.print(f"  [success][OK][/] {j.display_name} [muted]({human_readable_size(bytes_dl)})[/]")
                        summary.successful += 1
                        summary.total_bytes_downloaded += bytes_dl
                        downloaded_jobs.append(j)
                    except Exception as e:
                        err_msg = str(e)
                        progress.console.print(f"  [error][!][/] {j.display_name} [error][{_('Fallido')}: {err_msg}][/]")
                        summary.failed += 1
                        summary.errors.append(err_msg)
                        failed_jobs.append((j, err_msg))
                    finally:
                        progress.remove_task(tid)

        summary.total_duration = max(0.1, time.time() - start_time)

        console.print(f"[secondary]─[/] [primary]{_('RESUMEN DE DESCARGA')}[/] [secondary]───────────────────────────[/]")

        if failed_jobs or skipped_jobs:
            detalle_lines = []
            for job in downloaded_jobs[:10]:
                detalle_lines.append(f"  [primary]{job.display_name}[/] [success]: {_('Descargado')}[/]")
            if len(downloaded_jobs) > 10:
                detalle_lines.append(f"  [primary]{Template(_('... y $n archivos mas')).safe_substitute(n=len(downloaded_jobs) - 10)}[/] [success]: {_('Descargado')}s[/]")
            for job in skipped_jobs:
                detalle_lines.append(f"  [primary]{job.display_name}[/] [secondary]: {_('Omitido (ya existente)')}[/]")
            for job, err in failed_jobs:
                detalle_lines.append(f"  [primary]{job.display_name}[/] [error]: {_('Fallido')}: {err}[/]")
            console.print(Panel("\n".join(detalle_lines), title=_('Detalle de Operaciones'), expand=False))
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
            f"- [primary]{_('Archivos procesados:')}[/] {total_files}\n"
            f"  - [success]{_('Descargados con exito:')}[/] {summary.successful}\n"
            f"  - [secondary]{_('Omitidos (ya existentes):')}[/] {summary.skipped}\n"
            f"  - [error]{_('Fallidos con error:')}[/] {summary.failed}"
        )
        if not from_modules:
            metrics_content += (
                f"\n- [primary]{_('Total descargado:')}[/] {size_str}\n"
                f"- [primary]{_('Tiempo total:')}[/] {duration_str}\n"
                f"- [primary]{_('Velocidad media:')}[/] {speed_str}"
            )
        
        console.print(Panel(metrics_content, title=f"[success]{_('Métricas de Descarga')}[/]", expand=False, border_style="success"))
        console.print()

        return summary
