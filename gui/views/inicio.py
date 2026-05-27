import flet as ft
import json
import time
import threading
from pathlib import Path
from gui.theme import get_colors
from gui.config_manager import save_config
from gui.flet_compat import I, MC, pad, mar, border_all, border_only, dlg_open, dlg_close, snack_open, safe_update, accent_btn
from gui.system_utils import open_folder

_STATUS_BADGE = {
    "processing": ("⚙ Procesando", "accent",  "accent_bg"),
    "ok":         ("✅ Correcto",   "success", "success_bg"),
    "revision":   ("⚠ Revisión",   "warning", "warning_bg"),
    "error":      ("❌ Error",      "error",   "error_bg"),
}


def _build_output_index(output_dir: str, progress_cb=None) -> dict[str, bool]:
    """Scan output_dir for datos.json files. Returns {pdf_original_name: en_revision}.

    Indexes both the raw pdf_original value and a prefix-stripped version so that
    files processed via DEBUG_REPROCESS (where pdf_original includes the prefix like
    '_!_name.pdf') are still matched correctly even after the prefix changes.
    """
    result: dict[str, bool] = {}
    if not output_dir:
        return result
    base = Path(output_dir)
    if not base.exists():
        return result
    json_files = [
        f for f in base.rglob("datos.json")
        if "_borrados" not in f.parts
    ]
    total = len(json_files)
    for i, jp in enumerate(json_files):
        if progress_cb:
            progress_cb(i + 1, total)
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
            pdf_name = data.get("metadata", {}).get("pdf_original")
            en_rev   = bool(data.get("metadata", {}).get("en_revision", False))
            if pdf_name:
                result[pdf_name] = en_rev
                # Also index without any leading _X_ prefix (e.g. _!_, _DONE_) so
                # that lookup works even when the stored name includes a prefix or
                # the active prefix has changed since the file was processed.
                if pdf_name.startswith("_") and "_" in pdf_name[1:]:
                    second = pdf_name.index("_", 1)
                    stripped = pdf_name[second + 1:]
                    if stripped:
                        result.setdefault(stripped, en_rev)
        except Exception:
            continue
    return result


def _fmt_time(secs: float) -> str:
    secs = max(0, int(secs))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class InicioView:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.colors = get_colors(app.cfg.get("theme", "dark"))
        c = self.colors

        # Folder / filter state
        self._all_pdfs: list[Path] = []
        self._visible_pdfs: list[Path] = []
        self._selected: set[Path] = set()
        self._filter = "all"
        self._output_index: dict[str, bool] = {}   # pdf_original → en_revision
        self._scanning = False                      # guard against concurrent scans
        self._rescan_pending = False                # rescan requested while scan was running

        # Per-PDF status for the list display (managed locally in Avanzada)
        self._pdf_status: dict[Path, str] = {}

        # ── Folder fields ─────────────────────────────────────────
        self._input_field = ft.TextField(
            value=app.cfg.get("input_dir", ""),
            hint_text="Carpeta con los PDFs a procesar…",
            expand=True, bgcolor=c["input_bg"], border_color=c["border"],
            color=c["text"], border_radius=6, content_padding=pad(h=8, v=6),
            text_size=11, read_only=True,
        )
        self._output_field = ft.TextField(
            value=app.cfg.get("output_dir", ""),
            hint_text="Carpeta de salida (output)…",
            expand=True, bgcolor=c["input_bg"], border_color=c["border"],
            color=c["text"], border_radius=6, content_padding=pad(h=8, v=6),
            text_size=11, read_only=True,
        )

        # ── Scan stats ────────────────────────────────────────────
        self._stat_total     = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color=c["text"])
        self._stat_pending   = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color=c["warning"])
        self._stat_processed = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color=c["success"])
        self._stat_selected  = ft.Text("0", size=22, weight=ft.FontWeight.BOLD, color=c["accent"])

        # ── Filter buttons ────────────────────────────────────────
        self._btn_all  = self._filter_btn("Todos",      "all")
        self._btn_pend = self._filter_btn("Pendientes", "pending")
        self._btn_proc = self._filter_btn("Procesados", "processed")
        self._update_filter_buttons()

        # ── PDF list ──────────────────────────────────────────────
        self._pdf_list_view = ft.ListView(expand=True, spacing=0, padding=pad(right=4))

        # ── Output-scan progress bar (shown while cross-referencing) ──
        self._scan_progress_bar = ft.ProgressBar(
            value=0, color=c["accent"], bgcolor=c["border"], border_radius=4,
        )
        self._scan_progress_text = ft.Text(
            "Cotejando con output…", size=10, color=c["text_muted"],
        )
        self._scan_bar_container = ft.Container(
            visible=False,
            padding=pad(h=2, v=4),
            content=ft.Column([
                ft.Row([
                    ft.Icon(I.SYNC, size=11, color=c["accent"]),
                    self._scan_progress_text,
                ], spacing=4),
                self._scan_progress_bar,
            ], spacing=3),
        )

        # ── Process button ────────────────────────────────────────
        self._process_btn_wrapper = accent_btn(
            "Procesar PDFs", icon=I.PLAY_ARROW,
            on_click=self._on_process, colors=c,
        )
        self._process_btn = self._process_btn_wrapper.content  # OutlinedButton

        # ── Processing counters ───────────────────────────────────
        self._progress_text  = ft.Text("", size=11, color=c["text_muted"])
        self._proc_done_text = ft.Text("0/0", size=12, weight=ft.FontWeight.BOLD, color=c["text"])
        self._proc_ok_text   = ft.Text("0",   size=12, weight=ft.FontWeight.BOLD, color=c["success"])
        self._proc_rev_text  = ft.Text("0",   size=12, weight=ft.FontWeight.BOLD, color=c["warning"])
        self._proc_err_text  = ft.Text("0",   size=12, weight=ft.FontWeight.BOLD, color=c["error"])
        self._proc_elapsed   = ft.Text("00:00:00", size=11, color=c["text_muted"])
        self._proc_eta       = ft.Text("--:--:--", size=11, color=c["text_muted"])

        # ── Pause / Stop buttons (solo icono) ─────────────────────
        self._pause_btn = ft.IconButton(
            icon=I.PAUSE, icon_color=c["warning"], icon_size=18,
            tooltip="Pausar", on_click=self._on_pause_resume,
        )
        self._stop_btn = ft.IconButton(
            icon=I.STOP, icon_color=c["error"], icon_size=18,
            tooltip="Detener", on_click=self._on_stop,
        )

        # ── Log view ──────────────────────────────────────────────
        self._log_view = ft.ListView(expand=True, spacing=0, auto_scroll=True, padding=pad(all=8))

        # ── Processing section container ──────────────────────────
        self._processing_section = ft.Container(
            visible=True,
            bgcolor=c["surface"], border_radius=10,
            border=border_all(1, c["border"]), padding=pad(all=10),
            content=ft.Column([
                ft.Container(
                    bgcolor=c["card"], border_radius=8, padding=pad(h=12, v=8),
                    content=ft.Row([
                        ft.Column([
                            self._proc_done_text,
                            ft.Text("Procesados", size=10, color=c["text_muted"]),
                        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Container(width=1, height=32, bgcolor=c["border"]),
                        ft.Column([
                            self._proc_ok_text,
                            ft.Text("Correctos", size=10, color=c["text_muted"]),
                        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Container(width=1, height=32, bgcolor=c["border"]),
                        ft.Column([
                            self._proc_rev_text,
                            ft.Text("Revisión", size=10, color=c["text_muted"]),
                        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Container(width=1, height=32, bgcolor=c["border"]),
                        ft.Column([
                            self._proc_err_text,
                            ft.Text("Errores", size=10, color=c["text_muted"]),
                        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Container(expand=True),
                        ft.Column([
                            ft.Row([
                                ft.Icon(I.TIMER, size=12, color=c["text_muted"]),
                                ft.Text("Transcurrido", size=10, color=c["text_muted"]),
                            ], spacing=4),
                            self._proc_elapsed,
                        ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.END),
                        ft.Container(width=8),
                        ft.Column([
                            ft.Row([
                                ft.Icon(I.SCHEDULE, size=12, color=c["text_muted"]),
                                ft.Text("ETA", size=10, color=c["text_muted"]),
                            ], spacing=4),
                            self._proc_eta,
                        ], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.END),
                        ft.Container(width=4),
                        self._pause_btn,
                        self._stop_btn,
                    ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ),
                ft.Row([self._progress_text], spacing=0),
                ft.Row([
                    ft.Text("Log", size=11, weight=ft.FontWeight.W_600, color=c["text_dim"]),
                    ft.Container(expand=True),
                    ft.TextButton(
                        "Limpiar", icon=I.CLEAR_ALL,
                        style=ft.ButtonStyle(color=c["text_dim"]),
                        on_click=self._clear_log,
                    ),
                ]),
                ft.Container(
                    expand=True, bgcolor=c["card"], border_radius=8,
                    border=border_all(1, c["border"]), content=self._log_view,
                ),
            ], spacing=4, expand=True),
        )

        app.processing_mgr.add_observer(self)

        self.root = self._build()
        self._update_process_btn_state()
        if app.cfg.get("input_dir"):
            self._scan_pdfs()
        # If processing already running when this view is first created, show section
        if app.processing_mgr.is_processing:
            self._processing_section.visible = True
            self._update_process_btn_state()

    # ── Layout ────────────────────────────────────────────────────

    def _build(self) -> ft.Control:
        c = self.colors

        # ── Cabecera común (título + stats) ───────────────────────
        header = ft.Column([
            ft.Row([
                ft.IconButton(icon=I.REFRESH, icon_color=c["text_muted"],
                              tooltip="Recargar lista", on_click=lambda _: self._scan_pdfs()),
                ft.Text("Avanzada", size=20, weight=ft.FontWeight.BOLD, color=c["text"]),
                ft.Container(expand=True),
            ]),
            ft.Container(height=8),
            ft.Row([
                self._mini_stat("Total",      self._stat_total,     c["surface"]),
                self._mini_stat("Pendientes", self._stat_pending,   c["warning_bg"]),
                self._mini_stat("Procesados", self._stat_processed, c["success_bg"]),
                self._mini_stat("A procesar", self._stat_selected,  c["accent_bg"]),
            ], spacing=6),
            ft.Container(height=10),
        ], spacing=0)

        # ── Panel izquierdo: carpetas + botón ─────────────────────
        left = ft.Container(
            width=230, bgcolor=c["bg"], padding=pad(right=14),
            content=ft.Column([
                ft.Container(
                    bgcolor=c["surface"], border_radius=10,
                    border=border_all(1, c["border"]), padding=pad(all=8),
                    content=ft.Column([
                        ft.Text("PDFs de entrada", size=10, color=c["text_dim"]),
                        ft.Row([
                            self._input_field,
                            ft.IconButton(icon=I.FOLDER, icon_color=c["accent"], icon_size=16,
                                          tooltip="Seleccionar carpeta", on_click=self._pick_input),
                            ft.IconButton(icon=I.FOLDER_OPEN, icon_color=c["text_muted"], icon_size=16,
                                          tooltip="Abrir en explorador", on_click=self._open_input_folder),
                        ], spacing=2),
                        ft.Container(height=4),
                        ft.Text("Carpeta de salida", size=10, color=c["text_dim"]),
                        ft.Row([
                            self._output_field,
                            ft.IconButton(icon=I.FOLDER, icon_color=c["accent"], icon_size=16,
                                          tooltip="Seleccionar carpeta", on_click=self._pick_output),
                            ft.IconButton(icon=I.FOLDER_OPEN, icon_color=c["text_muted"], icon_size=16,
                                          tooltip="Abrir en explorador", on_click=self._open_output_folder),
                        ], spacing=2),
                    ], spacing=3),
                ),
                ft.Container(expand=True),
                self._process_btn_wrapper,
                ft.Container(height=4),
            ], expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        )

        # ── Panel derecho: lista + procesamiento ──────────────────
        right = ft.Container(
            expand=True,
            content=ft.Column([
                ft.Row([
                    self._btn_all, self._btn_pend, self._btn_proc,
                    ft.Container(expand=True),
                    ft.TextButton("Seleccionar todos", on_click=self._select_all,
                                  style=ft.ButtonStyle(color=c["text_muted"])),
                    ft.TextButton("Limpiar", on_click=self._clear_selection,
                                  style=ft.ButtonStyle(color=c["text_muted"])),
                ], spacing=4),
                ft.Container(height=4),
                ft.Container(
                    expand=2, bgcolor=c["surface"], border_radius=10,
                    border=border_all(1, c["border"]), padding=pad(all=8),
                    content=ft.Column([
                        self._scan_bar_container,
                        self._pdf_list_view,
                    ], spacing=4, expand=True),
                ),
                ft.Container(height=8),
                ft.Container(
                    expand=3,
                    content=self._processing_section,
                ),
            ], expand=True),
        )

        return ft.Container(
            expand=True, bgcolor=c["bg"], padding=pad(all=16),
            content=ft.Column([
                header,
                ft.Row(
                    [left, right], expand=True, spacing=0,
                    vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
            ], expand=True, spacing=0),
        )

    def _mini_stat(self, label: str, value_ctrl: ft.Text, bg_color: str) -> ft.Container:
        c = self.colors
        return ft.Container(
            expand=True, bgcolor=bg_color, border_radius=8, padding=pad(h=10, v=8),
            border=border_all(1, c["border"]),
            content=ft.Column([
                value_ctrl,
                ft.Text(label, size=10, color=c["text_muted"]),
            ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        )

    def _filter_btn(self, label: str, mode: str) -> ft.GestureDetector:
        c = self.colors
        is_sel = self._filter == mode
        inner = ft.Container(
            data=mode, padding=pad(h=14, v=7), border_radius=8,
            bgcolor=c["accent_bg"] if is_sel else c["surface"],
            border=border_all(1, c["accent"] if is_sel else c["border"]),
            ink=True, on_click=self._on_filter_click,
            content=ft.Text(
                label, size=12,
                color=c["accent_text"] if is_sel else c["text_muted"],
                weight=ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL,
            ),
        )

        def _hover(e, btn=inner, m=mode):
            c_now = self.colors
            active = self._filter == m
            base   = c_now["accent_bg"] if active else c_now["surface"]
            hovered = c_now["accent_bg"] if active else c_now["hover"]
            btn.bgcolor = hovered if e.data == "true" else base
            btn.update()

        return ft.GestureDetector(mouse_cursor=MC.CLICK, content=inner, on_hover=_hover)

    # ── PDF scanning ──────────────────────────────────────────────

    def _orig_name(self, pdf: Path) -> str:
        prefix = self.app.cfg.get("processed_prefix", "_!_")
        return pdf.name[len(prefix):] if pdf.name.startswith(prefix) else pdf.name

    def _is_in_index(self, pdf: Path) -> bool:
        name = pdf.name
        if name in self._output_index:
            return True
        prefixes = [self.app.cfg.get("processed_prefix", "_!_")]
        prefixes += self.app.cfg.get("processed_prefix_history", [])
        for pfx in prefixes:
            if not pfx:
                continue
            if name.startswith(pfx) and name[len(pfx):] in self._output_index:
                return True
            if f"{pfx}{name}" in self._output_index:
                return True
        return False

    def _scan_pdfs(self):
        if self._scanning:
            self._rescan_pending = True
            return
        input_dir = self.app.cfg.get("input_dir", "")
        if not input_dir:
            self._all_pdfs = []
            self._output_index = {}
            self._refresh_stats()
            self._apply_filter()
            self.page.update()
            return

        p = Path(input_dir)
        raw_pdfs = sorted(p.glob("*.pdf")) if p.exists() else []
        prefix = self.app.cfg.get("processed_prefix", "_!_")
        seen: dict[str, Path] = {}
        for pdf in raw_pdfs:
            base = self._orig_name(pdf)
            if base not in seen or pdf.name.startswith(prefix):
                seen[base] = pdf
        self._all_pdfs = sorted(seen.values())

        # Show list immediately with current state, then refine with output index
        self._refresh_stats()
        self._apply_filter()
        self._scan_bar_container.visible = True
        self._scan_progress_bar.value = 0
        self._scan_progress_text.value = "Cotejando con output…"
        self.page.update()

        self._scanning = True
        threading.Thread(target=self._scan_output_thread, daemon=True, name="OutputScan").start()

    def _scan_output_thread(self):
        out_dir = self.app.cfg.get("output_dir", "")
        _last_update = [time.monotonic()]

        def _progress(done, total):
            self._scan_progress_bar.value = done / total if total else 0
            self._scan_progress_text.value = f"Cotejando con output… ({done}/{total})"
            now = time.monotonic()
            if now - _last_update[0] >= 0.1 or done == total:
                _last_update[0] = now
                safe_update(self.page)

        self._output_index = _build_output_index(out_dir, _progress)

        # Auto-strip prefix from PDFs that have it but no output (crashed mid-process)
        prefix = self.app.cfg.get("processed_prefix", "_!_")
        old_prefixes = self.app.cfg.get("processed_prefix_history", [])
        any_renamed = False
        for pdf in list(self._all_pdfs):
            if pdf.name.startswith(prefix) and not self._is_in_index(pdf):
                try:
                    pdf.rename(pdf.parent / self._orig_name(pdf))
                    any_renamed = True
                except Exception:
                    pass

        # Rename old-prefix files to current prefix if they are in the index
        for old_pfx in old_prefixes:
            if not old_pfx or old_pfx == prefix:
                continue
            for pdf in list(self._all_pdfs):
                if pdf.name.startswith(old_pfx):
                    base = pdf.name[len(old_pfx):]
                    if base in self._output_index:
                        new_path = pdf.parent / f"{prefix}{base}"
                        try:
                            pdf.rename(new_path)
                            any_renamed = True
                        except Exception:
                            pass

        # Añadir prefijo a procesados que lo perdieron (pipeline completó pero rename falló)
        all_known_prefixes = [p for p in ([prefix] + old_prefixes) if p]
        for pdf in list(self._all_pdfs):
            if not any(pdf.name.startswith(pfx) for pfx in all_known_prefixes):
                if self._is_in_index(pdf):
                    new_path = pdf.parent / f"{prefix}{pdf.name}"
                    try:
                        pdf.rename(new_path)
                        any_renamed = True
                    except Exception:
                        pass

        if any_renamed:
            input_dir = self.app.cfg.get("input_dir", "")
            p = Path(input_dir)
            raw_pdfs = sorted(p.glob("*.pdf")) if p.exists() else []
            seen: dict[str, Path] = {}
            for pdf in raw_pdfs:
                base = self._orig_name(pdf)
                if base not in seen or pdf.name.startswith(prefix):
                    seen[base] = pdf
            self._all_pdfs = sorted(seen.values())

        self._scanning = False
        self._scan_bar_container.visible = False
        self._refresh_stats()
        self._apply_filter()
        safe_update(self.page)

        if self._rescan_pending:
            self._rescan_pending = False
            async def _do_rescan():
                self._scan_pdfs()
            self.page.run_task(_do_rescan)

    def _refresh_stats(self):
        total = len(self._all_pdfs)
        processed = sum(1 for p in self._all_pdfs if self._is_in_index(p))
        self._stat_total.value     = str(total)
        self._stat_processed.value = str(processed)
        self._stat_pending.value   = str(total - processed)
        self._stat_selected.value  = str(len(self._selected))

    def _apply_filter(self):
        if self._filter == "pending":
            self._visible_pdfs = [f for f in self._all_pdfs if not self._is_in_index(f)]
        elif self._filter == "processed":
            self._visible_pdfs = [f for f in self._all_pdfs if self._is_in_index(f)]
        else:
            self._visible_pdfs = list(self._all_pdfs)
        self._rebuild_pdf_list()

    def _rebuild_pdf_list(self):
        c = self.colors
        self._pdf_list_view.controls.clear()

        if not self._all_pdfs:
            msg = "Selecciona una carpeta de PDFs." if not self.app.cfg.get("input_dir") else "No se encontraron PDFs en la carpeta."
            self._pdf_list_view.controls.append(
                ft.Container(padding=pad(all=20), content=ft.Text(msg, color=c["text_dim"], italic=True)))
            return

        if not self._visible_pdfs:
            self._pdf_list_view.controls.append(
                ft.Container(padding=pad(all=20), content=ft.Text("No hay PDFs con este filtro.", color=c["text_dim"], italic=True)))
            return

        debug_reprocess = self.app.cfg.get("debug_reprocess", False)
        for pdf in self._visible_pdfs:
            is_selected  = pdf in self._selected
            display_name = self._orig_name(pdf)
            orig         = self._orig_name(pdf)
            in_index     = self._is_in_index(pdf)

            proc_status = self._pdf_status.get(pdf)
            if proc_status and proc_status in _STATUS_BADGE:
                badge_text = _STATUS_BADGE[proc_status][0]
                badge_fg   = c[_STATUS_BADGE[proc_status][1]]
                badge_bg   = c[_STATUS_BADGE[proc_status][2]]
            elif in_index:
                orig_key = orig if orig in self._output_index else None
                if not orig_key:
                    # found via prefix strip — find the actual key
                    for pfx in [self.app.cfg.get("processed_prefix", "_!_")] + self.app.cfg.get("processed_prefix_history", []):
                        if pfx and pdf.name.startswith(pfx):
                            candidate = pdf.name[len(pfx):]
                            if candidate in self._output_index:
                                orig_key = candidate
                                break
                en_rev = self._output_index.get(orig_key, False) if orig_key else False
                if en_rev:
                    badge_text = "⚠ Revisión"
                    badge_fg   = c["warning"]
                    badge_bg   = c["warning_bg"]
                else:
                    badge_text = "✅ Correcto"
                    badge_fg   = c["badge_processed"]
                    badge_bg   = c["badge_processed_bg"]
            else:
                badge_text = "⏳ Pendiente"
                badge_fg   = c["badge_pending"]
                badge_bg   = c["badge_pending_bg"]

            badge = ft.Container(
                content=ft.Text(badge_text, size=10, color=badge_fg),
                bgcolor=badge_bg, border_radius=3, padding=pad(h=5, v=1),
            )

            # Hide checkbox for already-processed files when not in debug_reprocess mode
            show_checkbox = debug_reprocess or not in_index
            if show_checkbox:
                checkbox_icon = ft.Icon(
                    I.CHECK_BOX if is_selected else I.CHECK_BOX_OUTLINE_BLANK,
                    size=14,
                    color=c["accent"] if is_selected else c["border"],
                )
            else:
                checkbox_icon = ft.Container(width=14, height=14)

            row_inner = ft.Container(
                padding=pad(h=6, v=3), border_radius=3,
                bgcolor=c["accent_bg"] if is_selected else "transparent",
                ink=show_checkbox,
                on_click=(lambda e, p=pdf: self._toggle_pdf(p)) if show_checkbox else None,
                content=ft.Row([
                    checkbox_icon,
                    ft.Icon(I.PICTURE_AS_PDF, color=c["text_muted"], size=13),
                    ft.Text(display_name, size=11, color=c["text"], expand=True, no_wrap=True),
                    badge,
                ], spacing=4),
            )
            _sel = is_selected

            def _hover_row(e, btn=row_inner, sel=_sel):
                c_now = self.colors
                base   = c_now["accent_bg"] if sel else "transparent"
                hovered = c_now["accent_bg"] if sel else c_now["hover"]
                btn.bgcolor = hovered if e.data == "true" else base
                btn.update()

            self._pdf_list_view.controls.append(
                ft.GestureDetector(mouse_cursor=MC.CLICK, content=row_inner, on_hover=_hover_row)
            )

    # ── Filter / selection ────────────────────────────────────────

    def _on_filter_click(self, e):
        self._filter = e.control.data
        self._update_filter_buttons()
        self._apply_filter()
        self.page.update()

    def _update_filter_buttons(self):
        c = self.colors
        for btn, mode in [(self._btn_all, "all"), (self._btn_pend, "pending"), (self._btn_proc, "processed")]:
            inner = btn.content  # GestureDetector → inner Container
            is_sel = self._filter == mode
            inner.bgcolor = c["accent_bg"] if is_sel else c["surface"]
            inner.border  = border_all(1, c["accent"] if is_sel else c["border"])
            txt = inner.content
            txt.color  = c["accent_text"] if is_sel else c["text_muted"]
            txt.weight = ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL

    def _toggle_pdf(self, pdf):
        if pdf in self._selected:
            self._selected.discard(pdf)
        elif self.app.cfg.get("debug_reprocess", False) or not self._is_in_index(pdf):
            self._selected.add(pdf)
        self._stat_selected.value = str(len(self._selected))
        self._rebuild_pdf_list()
        self._update_process_btn_label()
        self.page.update()

    def _select_all(self, _e):
        debug_reprocess = self.app.cfg.get("debug_reprocess", False)
        self._selected = set(
            p for p in self._visible_pdfs
            if debug_reprocess or not self._is_in_index(p)
        )
        self._stat_selected.value = str(len(self._selected))
        self._rebuild_pdf_list()
        self._update_process_btn_label()
        self.page.update()

    def _clear_selection(self, _e):
        self._selected.clear()
        self._stat_selected.value = "0"
        self._rebuild_pdf_list()
        self._update_process_btn_label()
        self.page.update()

    def _update_process_btn_label(self):
        n = len(self._selected)
        self._process_btn.text = f"Procesar ({n} PDF{'s' if n != 1 else ''})" if n else "Procesar PDFs"
        self._update_process_btn_state()

    def _update_process_btn_state(self):
        c = self.colors
        has_input  = bool(self.app.cfg.get("input_dir"))
        has_output = bool(self.app.cfg.get("output_dir"))
        has_sel    = bool(self._selected)
        disabled = self.app.processing_mgr.is_processing or self._scanning or not has_input or not has_output or not has_sel
        self._process_btn.disabled = disabled
        self._process_btn.style = ft.ButtonStyle(
            color=c["text_dim"] if disabled else c["accent"],
            side=ft.BorderSide(1, c["border"] if disabled else c["accent"]),
        )
        self._process_btn_wrapper.mouse_cursor = MC.FORBIDDEN if disabled else MC.CLICK

    # ── Refresh (called when navigating to this view) ─────────────

    def refresh(self):
        """Sync folder fields from config and rescan if not processing."""
        self._input_field.value = self.app.cfg.get("input_dir", "")
        self._output_field.value = self.app.cfg.get("output_dir", "")
        if not self.app.processing_mgr.is_processing:
            self._scan_pdfs()
        self._update_process_btn_state()

    # ── Startup folder checks (kept for potential direct use) ─────

    def check_folders_on_startup(self):
        input_dir = self.app.cfg.get("input_dir", "")
        input_ok = bool(input_dir) and Path(input_dir).exists()
        if not input_ok:
            self._show_input_folder_dialog(then=self._show_output_folder_dialog_if_needed)
        else:
            self._show_output_folder_dialog_if_needed()

    def _show_input_folder_dialog(self, then=None):
        c = self.colors
        input_dir = self.app.cfg.get("input_dir", "")
        if input_dir:
            msg = (f"La carpeta de PDFs configurada no existe:\n{input_dir}\n\n"
                   "¿Deseas seleccionar una diferente?")
        else:
            msg = "No hay ninguna carpeta de PDFs configurada.\n¿Deseas seleccionarla ahora?"

        async def _pick(e):
            dlg_close(self.page, dlg)
            path = await ft.FilePicker().get_directory_path(dialog_title="Seleccionar carpeta de PDFs")
            if path:
                self._input_field.value = path
                self.app.cfg["input_dir"] = path
                save_config(self.app.cfg)
                self._scan_pdfs()
                self._update_process_btn_state()
                self.page.update()
            if then:
                then()

        def _cancel(e):
            dlg_close(self.page, dlg)
            if then:
                then()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Carpeta de PDFs", color=c["text"]),
            content=ft.Text(msg, color=c["text_muted"], size=13),
            bgcolor=c["surface"],
            actions=[
                ft.TextButton("Cancelar", on_click=_cancel),
                accent_btn(
                    "Seleccionar carpeta", icon=I.FOLDER_OPEN,
                    on_click=lambda e: self.page.run_task(_pick, e), colors=c,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, dlg)

    def _show_output_folder_dialog_if_needed(self):
        output_dir = self.app.cfg.get("output_dir", "")
        output_ok = bool(output_dir) and Path(output_dir).exists()
        if output_ok:
            return

        c = self.colors
        can_create = bool(output_dir)
        if can_create:
            msg = (f"La carpeta de salida configurada no existe:\n{output_dir}\n\n"
                   "¿Deseas crearla o seleccionar una diferente?")
        else:
            msg = "No hay ninguna carpeta de salida configurada.\n¿Deseas seleccionarla ahora?"

        def _create(e):
            dlg_close(self.page, dlg)
            try:
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                self._output_field.value = output_dir
                self._update_process_btn_state()
                self.page.update()
                self._show_snack(f"Carpeta creada: {output_dir}")
            except Exception as ex:
                self._show_snack(f"Error al crear la carpeta: {ex}", error=True)

        async def _pick(e):
            dlg_close(self.page, dlg)
            path = await ft.FilePicker().get_directory_path(dialog_title="Seleccionar carpeta de salida")
            if path:
                self._output_field.value = path
                self.app.cfg["output_dir"] = path
                save_config(self.app.cfg)
                self._update_process_btn_state()
                self.page.update()

        actions = [
            ft.TextButton("Cancelar", on_click=lambda e: dlg_close(self.page, dlg)),
            ft.TextButton(
                "Seleccionar otra" if can_create else "Seleccionar carpeta",
                on_click=lambda e: self.page.run_task(_pick, e),
            ),
        ]
        if can_create:
            actions.append(accent_btn(
                "Crear carpeta", icon=I.CREATE_NEW_FOLDER,
                on_click=_create, colors=c,
            ))

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Carpeta de salida", color=c["text"]),
            content=ft.Text(msg, color=c["text_muted"], size=13),
            bgcolor=c["surface"],
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, dlg)

    # ── Folder pickers ────────────────────────────────────────────

    async def _pick_input(self, _e):
        path = await ft.FilePicker().get_directory_path(dialog_title="Seleccionar carpeta de PDFs")
        if path:
            self._input_field.value = path
            self.app.cfg["input_dir"] = path
            save_config(self.app.cfg)
            self._scan_pdfs()
            self._update_process_btn_state()
            self.page.update()

    async def _pick_output(self, _e):
        path = await ft.FilePicker().get_directory_path(dialog_title="Seleccionar carpeta de salida")
        if path:
            self._output_field.value = path
            self.app.cfg["output_dir"] = path
            save_config(self.app.cfg)
            self._update_process_btn_state()
            self.page.update()

    def _open_input_folder(self, _e):
        d = self.app.cfg.get("input_dir", "")
        if d:
            open_folder(d)
        else:
            self._show_snack("Primero selecciona una carpeta de PDFs.", error=True)

    def _open_output_folder(self, _e):
        d = self.app.cfg.get("output_dir", "")
        if d:
            open_folder(d)
        else:
            self._show_snack("Primero selecciona una carpeta de salida.", error=True)

    # ── Processing ────────────────────────────────────────────────

    def _on_process(self, _e):
        if not self._selected:
            self._show_snack("Selecciona al menos un PDF.", error=True)
            return
        if not self.app.cfg.get("output_dir"):
            self._show_snack("Configura la carpeta de salida primero.", error=True)
            return
        self.app.processing_mgr.start(sorted(self._selected), dict(self.app.cfg))

    def _on_pause_resume(self, _e):
        self.app.processing_mgr.pause()

    def _on_stop(self, _e):
        c = self.colors

        def _do_stop(e):
            dlg_close(self.page, dlg)
            self.app.processing_mgr.stop()
            self._update_process_btn_state()
            self._progress_text.value = "Detenido por el usuario."
            self.page.update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("¿Detener el procesamiento?", color=c["text"]),
            content=ft.Text(
                "Los PDFs ya procesados se conservarán.\n"
                "El PDF que se está procesando podría quedar incompleto.",
                color=c["text_muted"], size=13,
            ),
            bgcolor=c["surface"],
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: dlg_close(self.page, dlg)),
                ft.ElevatedButton(
                    "Detener", icon=I.STOP, bgcolor=c["error"], color="#ffffff",
                    on_click=_do_stop,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, dlg)

    def _clear_log(self, _e):
        self._log_view.controls.clear()
        mgr = self.app.processing_mgr
        import queue as _q
        while not mgr.log_q.empty():
            try:
                mgr.log_q.get_nowait()
            except _q.Empty:
                break
        self.page.update()

    # ── Observer callbacks ────────────────────────────────────────

    def on_proc_started(self):
        mgr = self.app.processing_mgr
        self._pdf_status = {p: "pending" for p in mgr.pdf_list}
        self._log_view.controls.clear()
        self._progress_text.value  = f"0 / {mgr.count_total}  |  Iniciando…"
        self._proc_done_text.value = f"0 / {mgr.count_total}"
        self._proc_ok_text.value   = "0"
        self._proc_rev_text.value  = "0"
        self._proc_err_text.value  = "0"
        self._proc_elapsed.value   = "00:00:00"
        self._proc_eta.value       = "--:--:--"
        self._processing_section.visible = True
        self._pause_btn.icon    = I.PAUSE
        self._pause_btn.tooltip = "Pausar"
        self._rebuild_pdf_list()
        self._update_process_btn_state()

    def on_pdf_start(self, pdf_path: Path):
        self._pdf_status[pdf_path] = "processing"
        self._progress_text.value = f"Procesando: {pdf_path.name}"
        self._rebuild_pdf_list()

    def on_pdf_done(self, pdf_path: Path, status: str):
        mgr = self.app.processing_mgr
        self._pdf_status[pdf_path] = status
        pct = mgr.count_done / mgr.count_total if mgr.count_total else 0
        self._proc_done_text.value = f"{mgr.count_done} / {mgr.count_total}"
        self._proc_ok_text.value   = str(mgr.count_ok)
        self._proc_rev_text.value  = str(mgr.count_rev)
        self._proc_err_text.value  = str(mgr.count_err)
        self._progress_text.value  = f"{int(pct * 100)}% completado — Último: {pdf_path.name}"
        self._rebuild_pdf_list()

    def on_timer_tick(self, logs, elapsed, eta, done, total, is_paused):
        c = self.colors
        for msg in logs:
            if "[ERROR]" in msg:
                color = c["error"]
            elif "[WARNING]" in msg:
                color = c["warning"]
            elif "correcto" in msg.lower() or "completado" in msg.lower():
                color = c["success"]
            else:
                color = c["text_muted"]
            self._log_view.controls.append(
                ft.Text(msg, size=11, color=color, font_family="monospace", no_wrap=True)
            )
        if len(self._log_view.controls) > 1000:
            del self._log_view.controls[:len(self._log_view.controls) - 1000]
        self._proc_elapsed.value = elapsed
        self._proc_eta.value     = eta
        if is_paused:
            self._pause_btn.icon    = I.PLAY_ARROW
            self._pause_btn.tooltip = "Reanudar"
        else:
            self._pause_btn.icon    = I.PAUSE
            self._pause_btn.tooltip = "Pausar"

    def on_finished(self, elapsed: float):
        self._update_process_btn_state()
        self._proc_elapsed.value  = _fmt_time(elapsed)
        self._proc_eta.value      = "00:00:00"
        self._progress_text.value = f"Completado en {_fmt_time(elapsed)}"
        self._scan_pdfs()
        self._show_completion_dialog(elapsed)

    def _show_completion_dialog(self, elapsed: float):
        c = self.colors
        mgr = self.app.processing_mgr
        out_dir = self.app.cfg.get("output_dir", "")

        def _open_out(e):
            dlg_close(self.page, dlg)
            if out_dir:
                open_folder(out_dir)

        def _chip(label, value, fg, bg):
            return ft.Container(
                bgcolor=bg, border_radius=6, padding=pad(h=10, v=6),
                content=ft.Column([
                    ft.Text(str(value), size=18, weight=ft.FontWeight.BOLD, color=fg),
                    ft.Text(label, size=10, color=c["text_muted"]),
                ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            )

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(I.CHECK_CIRCLE, color=c["success"], size=16),
                ft.Container(width=6),
                ft.Text("Procesamiento completado", color=c["text"], size=13,
                         weight=ft.FontWeight.BOLD),
            ]),
            content=ft.Column([
                ft.Row([
                    _chip("procesados", mgr.count_done, c["text"],    c["card"]),
                    _chip("correctos",  mgr.count_ok,   c["success"], c["success_bg"]),
                    _chip("revisión",   mgr.count_rev,  c["warning"], c["warning_bg"]),
                    _chip("errores",    mgr.count_err,  c["error"],   c["error_bg"]),
                ], spacing=6),
                ft.Row([
                    ft.Icon(I.TIMER, color=c["text_muted"], size=12),
                    ft.Text(f"Tiempo total: {_fmt_time(elapsed)}", size=11, color=c["text_muted"]),
                ], spacing=4),
            ], spacing=10, tight=True),
            bgcolor=c["surface"],
            actions=[
                ft.TextButton("Cerrar", on_click=lambda e: dlg_close(self.page, dlg)),
                accent_btn(
                    "Abrir carpeta", icon=I.FOLDER_OPEN,
                    on_click=_open_out, colors=c,
                    disabled=not bool(out_dir),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        try:
            dlg_open(self.page, dlg)
        except Exception:
            pass

    # ── Utils ─────────────────────────────────────────────────────

    def _show_snack(self, msg: str, error: bool = False):
        c = self.colors
        snack_open(self.page, msg, c["error"] if error else c["success"])
