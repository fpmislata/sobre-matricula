import re
import time
import queue
import threading
from datetime import datetime
from pathlib import Path
from gui.processing_worker import ProcessingWorker


def _fmt_time(secs: float) -> str:
    secs = max(0, int(secs))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _parse_historical_avg(log_dir: Path) -> float | None:
    """Segundos/PDF medios de las últimas ejecuciones (máx 5 logs)."""
    if not log_dir.exists():
        return None
    logs = sorted(log_dir.glob("procesado_*.log"), reverse=True)[:5]
    ts_re = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*PDF marcado como procesado")
    all_deltas: list[float] = []
    for log_path in logs:
        try:
            stem_parts = log_path.stem.split("_", 1)[1]   # YYYY-MM-DD_HH-MM-SS
            session_start = datetime.strptime(stem_parts, "%Y-%m-%d_%H-%M-%S")
            timestamps: list[datetime] = []
            for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = ts_re.match(line)
                if m:
                    timestamps.append(datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f"))
            if not timestamps:
                continue
            first = (timestamps[0] - session_start).total_seconds()
            if 0 < first < 600:
                all_deltas.append(first)
            for i in range(1, len(timestamps)):
                delta = (timestamps[i] - timestamps[i - 1]).total_seconds()
                if 0 < delta < 600:
                    all_deltas.append(delta)
        except Exception:
            continue
    return sum(all_deltas) / len(all_deltas) if all_deltas else None


class ProcessingManager:
    """Centralises processing state and distributes updates to all registered observers.

    Observer interface (implement only what you need):
        on_proc_started()
        on_pdf_start(pdf_path)
        on_pdf_done(pdf_path, status)
        on_timer_tick(logs, elapsed, eta, done, total, is_paused)
        on_finished(elapsed)
    """

    def __init__(self, app):
        self.app = app
        self.page = app.page

        self.is_processing: bool = False
        self.worker: ProcessingWorker | None = None
        self.pdf_list: list[Path] = []
        self.count_done: int = 0
        self.count_ok: int = 0
        self.count_rev: int = 0
        self.count_err: int = 0
        self.count_total: int = 0
        self.start_time: float = 0.0
        self.log_q: queue.Queue = queue.Queue()

        self._last_pdf_time: float = 0.0
        self._current_pdf_start: float = 0.0   # inicio del PDF en curso (no se resetea en done)
        self._pdf_times: list[float] = []
        self._historical_avg: float | None = None
        self._observers: list = []
        self._timer_stop = threading.Event()
        self._timer_thread: threading.Thread | None = None

    # ── Observer management ──────────────────────────────────────────

    def add_observer(self, obs) -> None:
        if obs not in self._observers:
            self._observers.append(obs)

    def remove_observer(self, obs) -> None:
        self._observers = [o for o in self._observers if o is not obs]

    def _notify(self, method: str, **kwargs) -> None:
        for obs in list(self._observers):
            cb = getattr(obs, method, None)
            if callable(cb):
                try:
                    cb(**kwargs)
                except Exception:
                    pass

    # ── Public API ───────────────────────────────────────────────────

    def start(self, pdf_list: list[Path], config_dict: dict) -> None:
        if self.is_processing:
            return
        self.is_processing = True
        self.pdf_list = list(pdf_list)
        self.count_done = 0
        self.count_ok = 0
        self.count_rev = 0
        self.count_err = 0
        self.count_total = len(pdf_list)
        self.start_time = time.time()
        self._last_pdf_time = self.start_time
        self._current_pdf_start = self.start_time
        self._pdf_times = []

        # ETA inicial: config guardada → parseo de logs como fallback
        self._historical_avg = self.app.cfg.get("avg_pdf_time") or None
        if not self._historical_avg:
            try:
                from gui.config_manager import get_logs_dir
                self._historical_avg = _parse_historical_avg(get_logs_dir())
            except Exception:
                self._historical_avg = None

        while not self.log_q.empty():
            try:
                self.log_q.get_nowait()
            except queue.Empty:
                break

        self._notify("on_proc_started")
        try:
            self.page.update()
        except Exception:
            pass

        self._timer_stop.clear()
        self._timer_thread = threading.Thread(
            target=self._timer_loop, daemon=True, name="ProcTimer"
        )
        self._timer_thread.start()

        self.worker = ProcessingWorker(
            config=config_dict,
            pdf_list=pdf_list,
            callbacks={
                "on_log":       self._on_log,
                "on_pdf_start": self._on_pdf_start,
                "on_pdf_done":  self._on_pdf_done,
                "on_finished":  self._on_finished,
            },
        )
        self.worker.start()

    def pause(self) -> None:
        if self.worker:
            if self.worker.is_paused:
                self.worker.resume()
            else:
                self.worker.pause()

    def stop(self) -> None:
        self._timer_stop.set()
        if self.worker:
            self.worker.stop()
        self.is_processing = False

    # ── Thread-safe update ───────────────────────────────────────────

    def _safe_update(self) -> None:
        """Schedule page.update() on Flet's event loop (safe from background threads)."""
        page = self.page
        async def _upd():
            page.update()
        try:
            self.page.run_task(_upd)
        except Exception:
            pass

    # ── Worker callbacks ─────────────────────────────────────────────

    def _on_log(self, message: str) -> None:
        self.log_q.put(message)

    def _on_pdf_start(self, pdf_path: Path) -> None:
        now = time.time()
        self._last_pdf_time = now
        self._current_pdf_start = now   # solo se actualiza aquí, no en done
        self._notify("on_pdf_start", pdf_path=pdf_path)
        self._safe_update()

    def _on_pdf_done(self, pdf_path: Path, status: str) -> None:
        now = time.time()
        self._pdf_times.append(now - self._last_pdf_time)
        self._last_pdf_time = now
        self._current_pdf_start = now   # evita time_on_current=18s antes de _on_pdf_start siguiente
        self.count_done += 1
        if status == "ok":
            self.count_ok += 1
        elif status == "revision":
            self.count_rev += 1
        else:
            self.count_err += 1
        self._notify("on_pdf_done", pdf_path=pdf_path, status=status)
        self._safe_update()

    def _on_finished(self) -> None:
        self._timer_stop.set()
        self.is_processing = False
        elapsed = time.time() - self.start_time if self.start_time else 0.0

        # Guardar avg actualizado en config para la próxima sesión
        if self._pdf_times:
            session_avg = sum(self._pdf_times) / len(self._pdf_times)
            old_avg = self.app.cfg.get("avg_pdf_time")
            # EMA α=0.3: pondera sesiones recientes sin descartar historial
            new_avg = old_avg * 0.7 + session_avg * 0.3 if old_avg else session_avg
            self.app.cfg["avg_pdf_time"] = round(new_avg, 2)
            try:
                from gui.config_manager import save_config
                save_config(self.app.cfg)
            except Exception:
                pass

        self._notify("on_finished", elapsed=elapsed)
        self._safe_update()

    # ── Timer loop ───────────────────────────────────────────────────

    def _timer_loop(self) -> None:
        while not self._timer_stop.wait(0.5):
            logs: list[str] = []
            while True:
                try:
                    logs.append(self.log_q.get_nowait())
                except queue.Empty:
                    break

            now = time.time()
            elapsed = _fmt_time(now - self.start_time) if self.start_time else "00:00:00"
            eta = "--:--:--"

            if self.count_done >= self.count_total > 0:
                eta = "00:00:00"
            elif self._pdf_times:
                # ETA real: media de últimos 10 × restantes, menos tiempo ya gastado en el actual
                avg = sum(self._pdf_times[-10:]) / len(self._pdf_times[-10:])
                time_on_current = now - self._current_pdf_start
                remaining_after_current = self.count_total - self.count_done - 1
                eta_secs = max(0.0, avg - time_on_current) + avg * remaining_after_current
                eta = _fmt_time(eta_secs)
            elif self._historical_avg and self.count_total > 0:
                # ETA inicial basada en ejecuciones anteriores
                time_on_current = now - self._current_pdf_start
                remaining_after_current = self.count_total - self.count_done - 1
                eta_secs = max(0.0, self._historical_avg - time_on_current) + self._historical_avg * remaining_after_current
                eta = _fmt_time(eta_secs)

            is_paused = bool(self.worker and self.worker.is_paused)

            self._notify(
                "on_timer_tick",
                logs=logs,
                elapsed=elapsed,
                eta=eta,
                done=self.count_done,
                total=self.count_total,
                is_paused=is_paused,
            )

            if logs or self.is_processing:
                self._safe_update()
