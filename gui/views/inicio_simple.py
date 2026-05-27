import flet as ft
import threading
from pathlib import Path
from gui.theme import get_colors
from gui.config_manager import save_config
from gui.flet_compat import I, MC, pad, border_all, dlg_open, dlg_close, snack_open, safe_update, accent_btn
from gui.system_utils import open_folder
from gui.views.inicio import _build_output_index, _fmt_time


class InicioSimpleView:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.colors = get_colors(app.cfg.get("theme", "dark"))
        c = self.colors

        self._all_pdfs: list[Path] = []
        self._output_index: dict[str, bool] = {}
        self._scanning = False
        self._rescan_pending = False

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

        # ── Stats ─────────────────────────────────────────────────
        self._stat_total     = ft.Text("0", size=28, weight=ft.FontWeight.BOLD, color=c["text"])
        self._stat_pending   = ft.Text("0", size=28, weight=ft.FontWeight.BOLD, color=c["warning"])
        self._stat_processed = ft.Text("0", size=28, weight=ft.FontWeight.BOLD, color=c["success"])
        self._stat_revision  = ft.Text("0", size=28, weight=ft.FontWeight.BOLD, color=c["error"])

        # ── Process button ────────────────────────────────────────
        self._process_btn_wrapper = accent_btn(
            "Procesar PDFs", icon=I.PLAY_ARROW,
            on_click=self._on_process, colors=c,
        )
        self._process_btn = self._process_btn_wrapper.content  # OutlinedButton
        self._process_btn.height = 52

        # ── Progress section ──────────────────────────────────────
        self._progress_bar = ft.ProgressBar(
            value=0, color=c["accent"], bgcolor=c["border"], border_radius=4,
        )
        self._prog_counter = ft.Text(
            "0 / 0 procesados", size=13,
            color=c["text"], weight=ft.FontWeight.W_500,
        )
        self._prog_elapsed = ft.Text("00:00:00", size=12, color=c["text_muted"])
        self._prog_eta     = ft.Text("--:--:--", size=12, color=c["text_muted"])

        self._pause_btn = ft.IconButton(
            icon=I.PAUSE, icon_color=c["warning"], icon_size=18,
            tooltip="Pausar", on_click=self._on_pause_resume,
        )
        self._stop_btn = ft.IconButton(
            icon=I.STOP, icon_color=c["error"], icon_size=18,
            tooltip="Detener", on_click=self._on_stop,
        )

        self._progress_section = ft.Container(
            visible=False,
            bgcolor=c["surface"], border_radius=10,
            border=border_all(1, c["border"]), padding=pad(h=16, v=14),
            content=ft.Column([
                self._progress_bar,
                ft.Container(height=8),
                ft.Row([
                    self._prog_counter,
                    ft.Container(expand=True),
                    ft.Row([
                        ft.Icon(I.TIMER, size=13, color=c["text_muted"]),
                        self._prog_elapsed,
                        ft.Container(width=10),
                        ft.Icon(I.SCHEDULE, size=13, color=c["text_muted"]),
                        ft.Text("ETA", size=11, color=c["text_muted"]),
                        self._prog_eta,
                        ft.Container(width=4),
                        self._pause_btn,
                        self._stop_btn,
                    ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=0),
        )

        app.processing_mgr.add_observer(self)

        self.root = self._build()
        self._update_process_btn_state()
        if app.cfg.get("input_dir"):
            self._scan_pdfs()
        if app.processing_mgr.is_processing:
            self._progress_section.visible = True
            self._update_process_btn_state()

    # ── Layout ────────────────────────────────────────────────────

    def _build(self) -> ft.Control:
        c = self.colors

        header = ft.Row([
            ft.IconButton(
                icon=I.REFRESH, icon_color=c["text_muted"],
                tooltip="Recargar estadísticas",
                on_click=lambda _: self._scan_pdfs(),
            ),
            ft.Text("Inicio", size=20, weight=ft.FontWeight.BOLD, color=c["text"]),
            ft.Container(expand=True),
        ])

        folder_card = ft.Container(
            bgcolor=c["surface"], border_radius=10,
            border=border_all(1, c["border"]), padding=pad(all=12),
            content=ft.Column([
                ft.Text("PDFs de entrada", size=10, color=c["text_dim"]),
                ft.Row([
                    self._input_field,
                    ft.IconButton(
                        icon=I.FOLDER, icon_color=c["accent"], icon_size=16,
                        tooltip="Seleccionar carpeta",
                        on_click=self._pick_input,
                    ),
                    ft.IconButton(
                        icon=I.FOLDER_OPEN, icon_color=c["text_muted"], icon_size=16,
                        tooltip="Abrir en explorador",
                        on_click=self._open_input,
                    ),
                ], spacing=2),
                ft.Container(height=8),
                ft.Text("Carpeta de salida", size=10, color=c["text_dim"]),
                ft.Row([
                    self._output_field,
                    ft.IconButton(
                        icon=I.FOLDER, icon_color=c["accent"], icon_size=16,
                        tooltip="Seleccionar carpeta",
                        on_click=self._pick_output,
                    ),
                    ft.IconButton(
                        icon=I.FOLDER_OPEN, icon_color=c["text_muted"], icon_size=16,
                        tooltip="Abrir en explorador",
                        on_click=self._open_output,
                    ),
                ], spacing=2),
            ], spacing=3),
        )

        stats_row = ft.Row([
            self._stat_card("Total",      self._stat_total,     c["surface"]),
            self._stat_card("Pendientes", self._stat_pending,   c["warning_bg"]),
            self._stat_card("Procesados", self._stat_processed, c["success_bg"]),
            self._stat_card("Revisión",   self._stat_revision,  c["error_bg"]),
        ], spacing=10)

        center_col = ft.Column([
            header,
            ft.Container(height=16),
            folder_card,
            ft.Container(height=16),
            stats_row,
            ft.Container(height=22),
            ft.Row([self._process_btn_wrapper], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=16),
            self._progress_section,
        ], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

        return ft.Container(
            expand=True, bgcolor=c["bg"],
            content=ft.Row([
                ft.Container(expand=True),
                ft.Container(
                    width=560,
                    padding=pad(v=32),
                    content=center_col,
                ),
                ft.Container(expand=True),
            ], expand=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

    def _stat_card(self, label: str, value_ctrl: ft.Text, bg_color: str) -> ft.Container:
        c = self.colors
        return ft.Container(
            expand=True, bgcolor=bg_color, border_radius=10,
            padding=pad(h=10, v=16),
            border=border_all(1, c["border"]),
            content=ft.Column([
                value_ctrl,
                ft.Text(label, size=11, color=c["text_muted"]),
            ], spacing=3, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        )

    # ── Refresh (called on subsequent navigations to this view) ──

    def refresh(self):
        self._input_field.value  = self.app.cfg.get("input_dir", "")
        self._output_field.value = self.app.cfg.get("output_dir", "")
        if not self.app.processing_mgr.is_processing:
            self._scan_pdfs()
        self._update_process_btn_state()

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
            self._update_process_btn_state()
            try:
                self.page.update()
            except Exception:
                pass
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
        self._refresh_stats()
        try:
            self.page.update()
        except Exception:
            pass

        self._scanning = True
        threading.Thread(target=self._scan_output_thread, daemon=True, name="SimpleScan").start()

    def _scan_output_thread(self):
        out_dir = self.app.cfg.get("output_dir", "")
        self._output_index = _build_output_index(out_dir)

        prefix = self.app.cfg.get("processed_prefix", "_!_")
        old_prefixes = self.app.cfg.get("processed_prefix_history", [])
        any_renamed = False

        # Auto-clean crashes: remove current prefix if not in index
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
        self._refresh_stats()
        self._update_process_btn_state()
        safe_update(self.page)

        if self._rescan_pending:
            self._rescan_pending = False
            async def _do_rescan():
                self._scan_pdfs()
            self.page.run_task(_do_rescan)

    def _refresh_stats(self):
        total     = len(self._all_pdfs)
        processed = sum(1 for p in self._all_pdfs if self._is_in_index(p))
        revision  = sum(1 for v in self._output_index.values() if v is True)
        self._stat_total.value     = str(total)
        self._stat_processed.value = str(processed)
        self._stat_pending.value   = str(total - processed)
        self._stat_revision.value  = str(revision)

    def _pending_pdfs(self) -> list[Path]:
        return sorted(p for p in self._all_pdfs if not self._is_in_index(p))

    # ── Button state ──────────────────────────────────────────────

    def _update_process_btn_state(self):
        mgr = self.app.processing_mgr
        c = self.colors
        has_input  = bool(self.app.cfg.get("input_dir"))
        has_output = bool(self.app.cfg.get("output_dir"))
        pending    = len(self._pending_pdfs())
        disabled   = mgr.is_processing or self._scanning or not has_input or not has_output or pending == 0
        self._process_btn.disabled = disabled
        self._process_btn.style = ft.ButtonStyle(
            color=c["text_dim"] if disabled else c["accent"],
            side=ft.BorderSide(1, c["border"] if disabled else c["accent"]),
        )
        self._process_btn_wrapper.mouse_cursor = MC.FORBIDDEN if disabled else MC.CLICK
        if pending > 0:
            self._process_btn.text = f"Procesar PDFs ({pending})"
        else:
            self._process_btn.text = "Procesar PDFs"

    # ── Processing ────────────────────────────────────────────────

    def _on_process(self, _e):
        pending = self._pending_pdfs()
        if not pending:
            self._show_snack("No hay PDFs pendientes de procesar.", error=True)
            return
        if not self.app.cfg.get("output_dir"):
            self._show_snack("Configura la carpeta de salida primero.", error=True)
            return
        self.app.processing_mgr.start(pending, dict(self.app.cfg))

    def _on_pause_resume(self, _e):
        self.app.processing_mgr.pause()

    def _on_stop(self, _e):
        c = self.colors

        def _do_stop(e):
            dlg_close(self.page, dlg)
            self.app.processing_mgr.stop()
            self._update_process_btn_state()
            self._prog_counter.value = "Detenido por el usuario."
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

    # ── Observer callbacks ────────────────────────────────────────

    def on_proc_started(self):
        mgr = self.app.processing_mgr
        self._progress_bar.value = 0
        self._prog_counter.value = f"0 / {mgr.count_total} procesados"
        self._prog_elapsed.value = "00:00:00"
        self._prog_eta.value     = "--:--:--"
        self._pause_btn.icon     = I.PAUSE
        self._pause_btn.tooltip  = "Pausar"
        self._progress_section.visible = True
        self._update_process_btn_state()

    def on_timer_tick(self, logs, elapsed, eta, done, total, is_paused):
        self._prog_elapsed.value = elapsed
        self._prog_eta.value     = eta
        self._prog_counter.value = f"{done} / {total} procesados"
        if total > 0:
            self._progress_bar.value = done / total
        if is_paused:
            self._pause_btn.icon    = I.PLAY_ARROW
            self._pause_btn.tooltip = "Reanudar"
        else:
            self._pause_btn.icon    = I.PAUSE
            self._pause_btn.tooltip = "Pausar"

    def on_pdf_done(self, pdf_path, status):
        self._update_process_btn_state()

    def on_finished(self, elapsed):
        self._progress_section.visible = False
        self._scan_pdfs()
        self._update_process_btn_state()

    # ── Startup folder checks ─────────────────────────────────────

    def check_folders_on_startup(self):
        input_dir = self.app.cfg.get("input_dir", "")
        input_ok  = bool(input_dir) and Path(input_dir).exists()

        def _after_all():
            cfg = self.app.cfg
            if (cfg.get("pending_reorganization", False)
                    and not cfg.get("skip_pending_reorganization", False)
                    and cfg.get("output_dir")):
                self._show_pending_reorg_snack()

        def _check_output():
            self._show_output_folder_dialog_mandatory(then=_after_all)

        if not input_ok:
            self._show_input_folder_dialog_mandatory(then=_check_output)
        else:
            _check_output()

    def _show_pending_reorg_snack(self):
        from gui.flet_compat import snack_open
        snack_open(
            self.page,
            "Hay una reorganización de output pendiente. "
            "Ve a Configuración → Nomenclatura → 'Reorganizar output'.",
            self.colors.get("warning", "#FFA500"),
            6000,
        )

    def _show_input_folder_dialog_mandatory(self, then=None):
        """Startup dialog for PDF folder — no cancel, repeats until a valid path is chosen."""
        c = self.colors
        input_dir = self.app.cfg.get("input_dir", "")
        if input_dir:
            msg = (f"La carpeta de PDFs configurada no existe:\n{input_dir}\n\n"
                   "Selecciona una carpeta válida para continuar.")
        else:
            msg = "No hay ninguna carpeta de PDFs configurada.\nDebes seleccionarla para continuar."

        async def _pick(e):
            dlg_close(self.page, dlg)
            path = await ft.FilePicker().get_directory_path(dialog_title="Seleccionar carpeta de PDFs")
            if path and Path(path).exists():
                self._input_field.value = path
                self.app.cfg["input_dir"] = path
                save_config(self.app.cfg)
                self._scan_pdfs()
                self._update_process_btn_state()
                self.page.update()
                if then:
                    then()
            else:
                self._show_input_folder_dialog_mandatory(then=then)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Carpeta de PDFs requerida", color=c["text"]),
            content=ft.Text(msg, color=c["text_muted"], size=13),
            bgcolor=c["surface"],
            actions=[
                accent_btn(
                    "Seleccionar carpeta", icon=I.FOLDER_OPEN,
                    on_click=lambda e: self.page.run_task(_pick, e), colors=c,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, dlg)

    def _show_output_folder_dialog_mandatory(self, then=None):
        """Startup dialog for output folder — no cancel, repeats until a valid path is chosen."""
        output_dir = self.app.cfg.get("output_dir", "")
        output_ok  = bool(output_dir) and Path(output_dir).exists()
        if output_ok:
            if then:
                then()
            return

        c = self.colors
        can_create = bool(output_dir)
        if can_create:
            msg = (f"La carpeta de salida configurada no existe:\n{output_dir}\n\n"
                   "Créala o selecciona una diferente para continuar.")
        else:
            msg = "No hay ninguna carpeta de salida configurada.\nDebes seleccionarla para continuar."

        def _create(e):
            dlg_close(self.page, dlg)
            try:
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                self._output_field.value = output_dir
                self._update_process_btn_state()
                self.page.update()
                self._show_snack(f"Carpeta creada: {output_dir}")
                if then:
                    then()
            except Exception as ex:
                self._show_snack(f"Error al crear la carpeta: {ex}", error=True)
                self._show_output_folder_dialog_mandatory(then=then)

        async def _pick(e):
            dlg_close(self.page, dlg)
            path = await ft.FilePicker().get_directory_path(dialog_title="Seleccionar carpeta de salida")
            if path and Path(path).exists():
                self._output_field.value = path
                self.app.cfg["output_dir"] = path
                save_config(self.app.cfg)
                self._update_process_btn_state()
                self.page.update()
                if then:
                    then()
            else:
                self._show_output_folder_dialog_mandatory(then=then)

        actions = [
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
            title=ft.Text("Carpeta de salida requerida", color=c["text"]),
            content=ft.Text(msg, color=c["text_muted"], size=13),
            bgcolor=c["surface"],
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, dlg)

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
        output_ok  = bool(output_dir) and Path(output_dir).exists()
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

    def _open_input(self, _e):
        d = self.app.cfg.get("input_dir", "")
        if d:
            open_folder(d)
        else:
            self._show_snack("Primero selecciona una carpeta de PDFs.", error=True)

    def _open_output(self, _e):
        d = self.app.cfg.get("output_dir", "")
        if d:
            open_folder(d)
        else:
            self._show_snack("Primero selecciona una carpeta de salida.", error=True)

    # ── Utils ─────────────────────────────────────────────────────

    def _show_snack(self, msg: str, error: bool = False):
        c = self.colors
        snack_open(self.page, msg, c["error"] if error else c["success"])
