import threading
from pathlib import Path


class ProcessingWorker:
    """Runs the PDF pipeline in a background thread with pause/stop support."""

    def __init__(self, config: dict, pdf_list: list[Path], callbacks: dict):
        self.config = config
        self.pdf_list = pdf_list
        self.callbacks = callbacks
        # Expected keys in callbacks: on_log, on_pdf_start, on_pdf_done, on_finished

        self._stop = threading.Event()
        self._pause = threading.Event()
        self._thread: threading.Thread | None = None
        self.is_running = False
        self.is_paused = False

    def start(self):
        self._stop.clear()
        self._pause.clear()
        self.is_running = True
        self.is_paused = False
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="ProcessingWorker"
        )
        self._thread.start()

    def pause(self):
        self._pause.set()
        self.is_paused = True

    def resume(self):
        self._pause.clear()
        self.is_paused = False

    def stop(self):
        self._stop.set()
        self._pause.clear()
        self.is_running = False

    def _run(self):
        try:
            from main import run_pipeline
            run_pipeline(
                config_dict=self.config,
                pdf_list=self.pdf_list,
                on_log=self.callbacks.get("on_log"),
                on_pdf_start=self.callbacks.get("on_pdf_start"),
                on_pdf_done=self.callbacks.get("on_pdf_done"),
                stop_event=self._stop,
                pause_event=self._pause,
            )
        except Exception as e:
            cb = self.callbacks.get("on_log")
            if cb:
                cb(f"ERROR FATAL EN WORKER: {e}")
        finally:
            self.is_running = False
            cb = self.callbacks.get("on_finished")
            if cb:
                cb()
