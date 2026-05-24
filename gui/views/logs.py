import flet as ft
from pathlib import Path
from gui.theme import get_colors
from gui.config_manager import get_logs_dir
from gui.flet_compat import I, pad, border_all, dlg_open, dlg_close


def _parse_log_date(lf: Path) -> tuple[str, str, str]:
    """Returns (year, month, day) from procesado_YYYY-MM-DD_HH-MM-SS.log"""
    try:
        stem = lf.stem.replace("procesado_", "", 1)
        date_part = stem.split("_")[0]
        y, m, d = date_part.split("-")
        return y, m, d
    except Exception:
        return "", "", ""


class LogsView:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.colors = get_colors(app.cfg.get("theme", "dark"))

        self._log_files: list[Path] = []
        self._filtered_files: list[Path] = []
        self._selected_file: Path | None = None
        self._search_query: str = ""
        self._filter_year  = "Todos"
        self._filter_month = "Todos"
        self._filter_day   = "Todos"

        c = self.colors
        self._file_list = ft.ListView(expand=True, spacing=2, padding=pad(right=4))
        self._content_lines = ft.ListView(expand=True, spacing=0, padding=pad(all=12), auto_scroll=False)
        self._search_field = ft.TextField(
            hint_text="Buscar en el log (ej: DNI, nombre, ERROR)…",
            prefix_icon=I.SEARCH, border_radius=8, on_change=self._on_search,
            bgcolor=c["input_bg"], border_color=c["border"], color=c["text"],
            hint_style=ft.TextStyle(color=c["text_dim"]), filled=True,
        )
        self._status_text = ft.Text("", size=11, color=c["text_dim"])

        self._dd_year  = ft.Dropdown(
            value="Todos", options=[ft.dropdown.Option("Todos")],
            bgcolor=c["input_bg"], border_color=c["border"], color=c["text"],
            border_radius=8, content_padding=pad(h=10, v=6), width=200, text_size=12,
            on_select=self._on_filter_change,
        )
        self._dd_month = ft.Dropdown(
            value="Todos", options=[ft.dropdown.Option("Todos")],
            bgcolor=c["input_bg"], border_color=c["border"], color=c["text"],
            border_radius=8, content_padding=pad(h=10, v=6), width=200, text_size=12,
            on_select=self._on_filter_change,
        )
        self._dd_day   = ft.Dropdown(
            value="Todos", options=[ft.dropdown.Option("Todos")],
            bgcolor=c["input_bg"], border_color=c["border"], color=c["text"],
            border_radius=8, content_padding=pad(h=10, v=6), width=200, text_size=12,
            on_select=self._on_filter_change,
        )

        self.root = self._build()

    # ── Layout ────────────────────────────────────────────────────

    def _build(self) -> ft.Control:
        c = self.colors
        return ft.Container(
            expand=True, bgcolor=c["bg"], padding=pad(all=20),
            content=ft.Column([
                ft.Row([
                    ft.IconButton(icon=I.REFRESH, icon_color=c["text_muted"], tooltip="Recargar lista de logs", on_click=lambda _: self.refresh()),
                    ft.Text("Logs de Ejecuciones", size=22, weight=ft.FontWeight.BOLD, color=c["text"]),
                    ft.Container(expand=True),
                ]),
                ft.Container(height=12),
                ft.Row([
                    # Left panel
                    ft.Container(
                        width=220, bgcolor=c["surface"], border_radius=12,
                        border=border_all(1, c["border"]), padding=pad(all=10),
                        content=ft.Column([
                            ft.Text("FILTROS", size=10, weight=ft.FontWeight.W_700, color=c["text_dim"]),
                            ft.Container(height=6),
                            ft.Column([
                                ft.Text("Año", size=11, color=c["text_muted"]),
                                self._dd_year,
                            ], spacing=3),
                            ft.Column([
                                ft.Text("Mes", size=11, color=c["text_muted"]),
                                self._dd_month,
                            ], spacing=3),
                            ft.Column([
                                ft.Text("Día", size=11, color=c["text_muted"]),
                                self._dd_day,
                            ], spacing=3),
                            ft.Divider(height=1, color=c["border"]),
                            ft.Text("EJECUCIONES", size=10, weight=ft.FontWeight.W_700, color=c["text_dim"]),
                            ft.Container(height=4),
                            self._file_list,
                            ft.Divider(height=1, color=c["border"]),
                            ft.Row([
                                ft.TextButton(
                                    "Borrar actual", icon=I.DELETE_OUTLINE,
                                    style=ft.ButtonStyle(color=c["error"]),
                                    on_click=self._delete_current,
                                ),
                            ]),
                            ft.Row([
                                ft.TextButton(
                                    "Borrar todos", icon=I.DELETE_FOREVER,
                                    style=ft.ButtonStyle(color=c["error"]),
                                    on_click=self._delete_all,
                                ),
                            ]),
                        ], expand=True, spacing=6),
                    ),
                    # Right panel
                    ft.Container(
                        expand=True, width=700, bgcolor=c["surface"], border_radius=12,
                        border=border_all(1, c["border"]), padding=pad(all=12),
                        content=ft.Column([
                            self._search_field,
                            self._status_text,
                            ft.Container(height=4),
                            self._content_lines,
                        ], expand=True, spacing=4),
                    ),
                ],
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                ),
            ], expand=True),
        )

    # ── Public API ────────────────────────────────────────────────

    def refresh(self):
        self.colors = get_colors(self.app.cfg.get("theme", "dark"))
        logs_dir = get_logs_dir(self.app.cfg)
        self._log_files = (
            sorted(logs_dir.glob("procesado_*.log"), reverse=True)
            if logs_dir.exists() else []
        )
        self._rebuild_filter_options()
        self._apply_date_filter()
        self.page.update()

    # ── Filter logic ──────────────────────────────────────────────

    def _rebuild_filter_options(self):
        """Populate year/month/day options independently from all log files."""
        dates = [_parse_log_date(f) for f in self._log_files]

        years  = sorted({y for y, m, d in dates if y}, reverse=True)
        months = sorted({m for y, m, d in dates if m})
        days   = sorted({d for y, m, d in dates if d})

        self._dd_year.options  = [ft.dropdown.Option("Todos")] + [ft.dropdown.Option(v) for v in years]
        self._dd_month.options = [ft.dropdown.Option("Todos")] + [ft.dropdown.Option(v) for v in months]
        self._dd_day.options   = [ft.dropdown.Option("Todos")] + [ft.dropdown.Option(v) for v in days]

        # Reset any selected value that no longer exists
        if self._filter_year  not in ["Todos"] + years:
            self._filter_year  = "Todos"; self._dd_year.value  = "Todos"
        if self._filter_month not in ["Todos"] + months:
            self._filter_month = "Todos"; self._dd_month.value = "Todos"
        if self._filter_day   not in ["Todos"] + days:
            self._filter_day   = "Todos"; self._dd_day.value   = "Todos"

    def _on_filter_change(self, e):
        self._filter_year  = self._dd_year.value  or "Todos"
        self._filter_month = self._dd_month.value or "Todos"
        self._filter_day   = self._dd_day.value   or "Todos"
        self._apply_date_filter()
        self._file_list.update()

    def _apply_date_filter(self):
        self._filtered_files = []
        for lf in self._log_files:
            y, m, d = _parse_log_date(lf)
            if self._filter_year  != "Todos" and y != self._filter_year:  continue
            if self._filter_month != "Todos" and m != self._filter_month: continue
            if self._filter_day   != "Todos" and d != self._filter_day:   continue
            self._filtered_files.append(lf)
        self._rebuild_file_list()

    def _rebuild_file_list(self):
        self._file_list.controls.clear()
        if not self._filtered_files:
            self._file_list.controls.append(
                ft.Text("Sin logs.", size=12, color=self.colors["text_dim"], italic=True)
            )
        else:
            for lf in self._filtered_files:
                name = lf.stem.replace("procesado_", "")
                is_sel = lf == self._selected_file
                self._file_list.controls.append(self._file_item(lf, name, is_sel))

        if self._filtered_files and self._selected_file not in self._filtered_files:
            self._selected_file = self._filtered_files[0]
            self._load_content()

    # ── File item ─────────────────────────────────────────────────

    def _file_item(self, lf: Path, name: str, selected: bool) -> ft.Control:
        c = self.colors
        return ft.Container(
            data=lf, padding=pad(h=8, v=7), border_radius=6,
            bgcolor=c["accent_bg"] if selected else "transparent",
            ink=True, on_click=self._on_file_click,
            content=ft.Column([
                ft.Text(
                    name[:19], size=12, font_family="monospace",
                    color=c["accent_text"] if selected else c["text"],
                    weight=ft.FontWeight.W_600 if selected else ft.FontWeight.NORMAL,
                ),
                ft.Text(
                    f"{lf.stat().st_size // 1024} KB" if lf.exists() else "",
                    size=10, color=c["text_dim"],
                ),
            ], spacing=2),
        )

    def _on_file_click(self, e):
        self._selected_file = e.control.data
        self._load_content()
        self._rebuild_file_list()
        self.page.update()

    def _load_content(self):
        if not self._selected_file or not self._selected_file.exists():
            self._content_lines.controls.clear()
            self._content_lines.controls.append(
                ft.Text("Selecciona una ejecución de la lista.", color=self.colors["text_dim"], italic=True)
            )
            self._status_text.value = ""
            self.page.update()
            return
        try:
            lines = self._selected_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as ex:
            lines = [f"Error leyendo log: {ex}"]
        self._render_lines(lines)
        self.page.update()

    def _on_search(self, e):
        self._search_query = (e.control.value or "").strip()
        if self._selected_file:
            try:
                lines = self._selected_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                lines = []
            self._render_lines(lines)
            self.page.update()

    def _render_lines(self, lines: list[str]):
        c = self.colors
        q = self._search_query.lower()
        self._content_lines.controls.clear()
        matched = 0
        for line in lines:
            if q and q not in line.lower():
                continue
            matched += 1
            if "[ERROR]" in line:
                color = c["error"]
            elif "[WARNING]" in line:
                color = c["warning"]
            elif "revisión" in line.lower() or "revision" in line.lower():
                color = c["warning"]
            elif "completado" in line.lower() or "correcto" in line.lower():
                color = c["success"]
            else:
                color = c["text_muted"]
            self._content_lines.controls.append(
                ft.Text(line, size=11, color=color, font_family="monospace", selectable=True, no_wrap=True)
            )
        if q:
            self._status_text.value = (
                f"{matched} coincidencia(s) para '{self._search_query}'"
                if matched else f"Sin resultados para '{self._search_query}'"
            )
        else:
            self._status_text.value = f"{len(lines)} líneas" if lines else ""

    # ── Delete ────────────────────────────────────────────────────

    def _delete_current(self, _e):
        if not self._selected_file or not self._selected_file.exists():
            return
        c = self.colors
        target = self._selected_file

        def _confirm(e):
            dlg_close(self.page, dlg)
            try:
                target.unlink()
            except Exception:
                pass
            self._selected_file = None
            self.refresh()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("¿Borrar este log?", color=c["text"]),
            content=ft.Text(f"Se eliminará: {target.name}", color=c["text_muted"], size=13),
            bgcolor=c["surface"],
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: dlg_close(self.page, dlg)),
                ft.ElevatedButton("Borrar", bgcolor=c["error"], color="#ffffff", on_click=_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, dlg)

    def _delete_all(self, _e):
        c = self.colors
        count = len(self._log_files)

        def _confirm(e):
            dlg_close(self.page, dlg)
            for lf in self._log_files:
                try:
                    lf.unlink()
                except Exception:
                    pass
            self._selected_file = None
            self.refresh()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("¿Borrar todos los logs?", color=c["text"]),
            content=ft.Text(f"Se eliminarán {count} fichero(s) de log. Esta acción no se puede deshacer.", color=c["text_muted"], size=13),
            bgcolor=c["surface"],
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: dlg_close(self.page, dlg)),
                ft.ElevatedButton("Borrar todos", bgcolor=c["error"], color="#ffffff", on_click=_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, dlg)
