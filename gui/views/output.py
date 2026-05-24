import flet as ft
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from gui.theme import get_colors
from gui.config_manager import get_logs_dir
from gui.flet_compat import I, MC, pad, mar, border_all, dlg_open, dlg_close, action_icon_btn
from gui.system_utils import open_folder, open_file

_SKIP_DIRS = {"_borrados", "revision"}

_HEADER_LABELS = {
    "expediente": "Expediente",
    "dni":        "DNI/NIE",
    "nombre":     "Nombre",
    "apellido1":  "Apellido 1",
    "apellido2":  "Apellido 2",
    "ciclo":      "Ciclo",
    "anio":       "Año",
    "turno":      "Asistencia",
    "estado":     "Estado",
}


def _trash_dir(output_dir: str) -> Path:
    return Path(output_dir) / "_borrados"


def _count_trash(output_dir: str) -> int:
    """Returns count of expedientes in trash via datos.json; -1 if trash has content but no datos.json."""
    td = _trash_dir(output_dir)
    if not td.exists():
        return 0
    count = sum(1 for _ in td.rglob("datos.json"))
    if count == 0 and any(td.iterdir()):
        return -1  # has files but no datos.json (old structure)
    return count


@dataclass
class ExpedienteRow:
    folder: Path
    expediente: str
    dni: str
    nombre: str
    apellido1: str
    apellido2: str
    ciclo: str
    anio: str
    turno: str
    en_revision: bool
    motivos: list
    json_path: Path
    pdf_path: Path | None = None
    foto_path: Path | None = None


def _load_folder(folder: Path) -> ExpedienteRow | None:
    json_path = folder / "datos.json"
    if not json_path.exists():
        return None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    doc   = data.get("documento", {})
    ciclo = data.get("ciclo", {})
    curso = data.get("curso", {})
    meta  = data.get("metadata", {})

    anio_ini = str(curso.get("inicio", ""))
    anio_fin = str(curso.get("fin", ""))
    anio = f"{anio_ini[-2:]}/{anio_fin[-2:]}" if anio_ini and anio_fin else anio_ini or anio_fin

    pdf_candidates = list(folder.glob("*.pdf"))
    pdf_path = pdf_candidates[0] if pdf_candidates else None
    foto_candidates = [folder / "foto.jpg", folder / "foto_carnet.jpg", folder / "foto_dni.jpg"]
    foto_path = next((f for f in foto_candidates if f.exists()), None)

    return ExpedienteRow(
        folder=folder,
        expediente=str(data.get("expediente") or ""),
        dni=str(doc.get("numero_verificado") or ""),
        nombre=str(data.get("nombre") or ""),
        apellido1=str(data.get("apellido1") or ""),
        apellido2=str(data.get("apellido2") or ""),
        ciclo=str(ciclo.get("codigo") or ""),
        anio=anio,
        turno=str(data.get("tipo_asistencia") or ""),
        en_revision=bool(meta.get("en_revision", False)),
        motivos=meta.get("motivos_revision") or [],
        json_path=json_path,
        pdf_path=pdf_path,
        foto_path=foto_path,
    )


def _load_expedientes(output_dir: str) -> list[ExpedienteRow]:
    rows = []
    if not output_dir:
        return rows
    base = Path(output_dir)
    if not base.exists():
        return rows

    # Scan recursivo: soporta jerarquía arbitraria de subcarpetas.
    # Excluye _borrados, revision y debug (revision se carga explícitamente abajo).
    json_files = [
        f for f in base.rglob("datos.json")
        if "_borrados" not in f.parts
        and "revision" not in f.parts
        and "debug" not in f.parts
    ]
    for jp in sorted(json_files):
        row = _load_folder(jp.parent)
        if row:
            rows.append(row)

    # Revisión siempre plana: output/revision/{dni,foto,datos}/{expediente}/
    revision_base = base / "revision"
    if revision_base.exists():
        for subdir in sorted(revision_base.iterdir()):
            if not subdir.is_dir():
                continue
            for folder in sorted(subdir.iterdir()):
                if not folder.is_dir():
                    continue
                row = _load_folder(folder)
                if row:
                    rows.append(row)

    return rows


class OutputView:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.colors = get_colors(app.cfg.get("theme", "dark"))
        c = self.colors

        self._all_rows: list[ExpedienteRow] = []
        self._filtered_rows: list[ExpedienteRow] = []

        self._filter_estado  = "todos"
        self._filter_ciclo   = "Todos"
        self._filter_anio    = "Todos"
        self._filter_turno   = "Todos"
        self._filter_search  = ""

        self._sort_col: str | None = None
        self._sort_reverse: bool = False
        self._header_cells: dict[str, tuple[ft.Text, ft.Icon]] = {}

        # Filter controls
        self._dd_estado = ft.Dropdown(
            value="todos",
            options=[
                ft.dropdown.Option("todos",    "Todos"),
                ft.dropdown.Option("correcto", "Solo correctos"),
                ft.dropdown.Option("revision", "Solo revisión"),
            ],
            bgcolor=c["input_bg"], border_color=c["border"], color=c["text"],
            border_radius=8, content_padding=pad(h=10, v=6), width=150, text_size=12,
            on_select=self._on_filter_change,
        )
        self._dd_ciclo = ft.Dropdown(
            value="Todos", options=[ft.dropdown.Option("Todos")],
            bgcolor=c["input_bg"], border_color=c["border"], color=c["text"],
            border_radius=8, content_padding=pad(h=10, v=6), width=110, text_size=12,
            on_select=self._on_filter_change,
        )
        self._dd_anio = ft.Dropdown(
            value="Todos", options=[ft.dropdown.Option("Todos")],
            bgcolor=c["input_bg"], border_color=c["border"], color=c["text"],
            border_radius=8, content_padding=pad(h=10, v=6), width=95, text_size=12,
            on_select=self._on_filter_change,
        )
        self._dd_turno = ft.Dropdown(
            value="Todos", options=[ft.dropdown.Option("Todos")],
            bgcolor=c["input_bg"], border_color=c["border"], color=c["text"],
            border_radius=8, content_padding=pad(h=10, v=6), width=130, text_size=12,
            on_select=self._on_filter_change,
        )
        self._search_field = ft.TextField(
            hint_text="Buscar…", prefix_icon=I.SEARCH,
            border_radius=8, expand=True,
            bgcolor=c["input_bg"], border_color=c["border"], color=c["text"],
            hint_style=ft.TextStyle(color=c["text_dim"]),
            on_change=self._on_search_change,
        )
        self._count_text = ft.Text("", size=12, color=c["text_dim"])
        self._table_container = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, spacing=0)

        self._trash_label = ft.Text("Papelera vacía", size=13, color=c["text_dim"])
        self._trash_icon  = ft.Icon(I.DELETE_FOREVER, size=16, color=c["text_dim"])
        self._trash_btn = ft.OutlinedButton(
            content=ft.Row([
                self._trash_icon,
                self._trash_label,
            ], tight=True, spacing=6),
            style=ft.ButtonStyle(
                color=c["text_dim"],
                side=ft.BorderSide(1, c["border"]),
            ),
            on_click=self._empty_trash,
            disabled=True,
        )
        self._trash_btn_wrapper = ft.GestureDetector(
            mouse_cursor=MC.FORBIDDEN,
            content=self._trash_btn,
            visible=True,
            on_hover=self._on_trash_hover,
        )
        self._open_trash_btn = ft.IconButton(
            icon=I.FOLDER_OPEN,
            icon_color=c["text_dim"],
            tooltip="Abrir carpeta papelera",
            disabled=True,
            on_click=self._open_trash_folder,
        )
        self._open_trash_wrapper = ft.GestureDetector(
            mouse_cursor=MC.FORBIDDEN,
            content=self._open_trash_btn,
            visible=True,
        )

        self.root = self._build()

    # ── Layout ────────────────────────────────────────────────────

    def _sort_icon_name(self, col: str):
        if self._sort_col != col:
            return I.UNFOLD_MORE
        return I.ARROW_UPWARD if not self._sort_reverse else I.ARROW_DOWNWARD

    def _make_header_cell(self, col: str, width: int) -> ft.GestureDetector:
        c = self.colors
        label = _HEADER_LABELS.get(col, col)
        is_active = self._sort_col == col
        txt = ft.Text(
            label, size=10, weight=ft.FontWeight.W_700,
            color=c["accent"] if is_active else c["text_dim"],
        )
        icon = ft.Icon(
            self._sort_icon_name(col), size=11,
            color=c["accent"] if is_active else c["text_dim"],
        )
        self._header_cells[col] = (txt, icon)
        return ft.GestureDetector(
            content=ft.Container(
                width=width,
                content=ft.Row([txt, icon], spacing=2, tight=True),
            ),
            mouse_cursor=ft.MouseCursor.CLICK,
            on_tap=lambda e, col=col: self._on_sort(col),
        )

    def _build(self) -> ft.Control:
        c = self.colors
        return ft.Container(
            expand=True, bgcolor=c["bg"], padding=pad(all=20),
            content=ft.Column([
                ft.Row([
                    ft.GestureDetector(
                        mouse_cursor=MC.CLICK,
                        content=ft.Container(
                            content=ft.IconButton(
                                icon=I.REFRESH, icon_color=c["text_muted"],
                                tooltip="Recargar expedientes",
                                on_click=lambda _: self.refresh(),
                            ),
                            border_radius=8,
                        ),
                        on_hover=lambda e: (
                            setattr(e.control.content, "bgcolor",
                                    self.colors["hover"] if e.data == "true" else None)
                            or e.control.content.update()
                        ),
                    ),
                    ft.Text("Expedientes", size=22, weight=ft.FontWeight.BOLD, color=c["text"]),
                    ft.Container(expand=True),
                    self._open_trash_wrapper,
                    self._trash_btn_wrapper,
                ]),
                ft.Container(height=10),

                # Filters
                ft.Container(
                    bgcolor=c["surface"], border_radius=10,
                    border=border_all(1, c["border"]), padding=pad(h=14, v=10),
                    content=ft.Row([
                        ft.Text("Estado:", size=12, color=c["text_muted"]), self._dd_estado,
                        ft.Text("Ciclo:",  size=12, color=c["text_muted"]), self._dd_ciclo,
                        ft.Text("Año:",    size=12, color=c["text_muted"]), self._dd_anio,
                        ft.Text("Turno:",  size=12, color=c["text_muted"]), self._dd_turno,
                        self._search_field,
                    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ),
                ft.Container(height=8),
                self._count_text,
                ft.Container(height=4),

                # Table header
                ft.Container(
                    bgcolor=c["card"], border_radius=8, padding=pad(h=10, v=5),
                    border=border_all(1, c["border"]),
                    content=ft.Row([
                        self._make_header_cell("expediente", 70),
                        self._make_header_cell("dni",        100),
                        self._make_header_cell("nombre",     85),
                        self._make_header_cell("apellido1",  85),
                        self._make_header_cell("apellido2",  70),
                        self._make_header_cell("ciclo",      50),
                        self._make_header_cell("anio",       45),
                        self._make_header_cell("turno",      80),
                        self._make_header_cell("estado",     70),
                        ft.Container(expand=True),
                        ft.Text("Acciones", size=10, weight=ft.FontWeight.W_700, color=c["text_dim"], width=160),
                    ], spacing=4),
                ),

                # Rows
                ft.Container(
                    expand=True, bgcolor=c["surface"], border_radius=10,
                    border=border_all(1, c["border"]),
                    content=self._table_container,
                ),
            ], expand=True),
        )

    # ── Public API ────────────────────────────────────────────────

    def refresh(self):
        self.colors = get_colors(self.app.cfg.get("theme", "dark"))
        out_dir = self.app.cfg.get("output_dir", "")
        self._all_rows = _load_expedientes(out_dir)
        self._rebuild_filter_options()
        self._apply_filters()
        self._update_trash_btn()
        self.page.update()

    # ── Filters ───────────────────────────────────────────────────

    def _rebuild_filter_options(self):
        ciclos  = sorted({r.ciclo  for r in self._all_rows if r.ciclo})
        anios   = sorted({r.anio   for r in self._all_rows if r.anio}, reverse=True)
        turnos  = sorted({r.turno  for r in self._all_rows if r.turno})

        self._dd_ciclo.options = [ft.dropdown.Option("Todos")] + [ft.dropdown.Option(c) for c in ciclos]
        self._dd_anio.options  = [ft.dropdown.Option("Todos")] + [ft.dropdown.Option(a) for a in anios]
        self._dd_turno.options = [ft.dropdown.Option("Todos")] + [ft.dropdown.Option(t) for t in turnos]

        if self._filter_ciclo not in ["Todos"] + ciclos:
            self._filter_ciclo = "Todos"; self._dd_ciclo.value = "Todos"
        if self._filter_anio  not in ["Todos"] + anios:
            self._filter_anio  = "Todos"; self._dd_anio.value  = "Todos"
        if self._filter_turno not in ["Todos"] + turnos:
            self._filter_turno = "Todos"; self._dd_turno.value = "Todos"

    def _on_filter_change(self, e):
        self._filter_estado = self._dd_estado.value or "todos"
        self._filter_ciclo  = self._dd_ciclo.value  or "Todos"
        self._filter_anio   = self._dd_anio.value   or "Todos"
        self._filter_turno  = self._dd_turno.value  or "Todos"
        self._apply_filters()
        self.page.update()

    def _on_search_change(self, e):
        self._filter_search = (e.control.value or "").strip().lower()
        self._apply_filters()
        self.page.update()

    def _apply_filters(self):
        rows = self._all_rows
        if self._filter_estado == "correcto":
            rows = [r for r in rows if not r.en_revision]
        elif self._filter_estado == "revision":
            rows = [r for r in rows if r.en_revision]
        if self._filter_ciclo != "Todos":
            rows = [r for r in rows if r.ciclo == self._filter_ciclo]
        if self._filter_anio != "Todos":
            rows = [r for r in rows if r.anio == self._filter_anio]
        if self._filter_turno != "Todos":
            rows = [r for r in rows if r.turno == self._filter_turno]
        if self._filter_search:
            q = self._filter_search
            rows = [r for r in rows if
                q in r.expediente.lower() or q in r.dni.lower() or
                q in r.nombre.lower() or q in r.apellido1.lower() or
                q in r.apellido2.lower() or q in r.ciclo.lower() or
                q in r.turno.lower()]
        if self._sort_col:
            key_map = {
                "expediente": lambda r: r.expediente,
                "dni":        lambda r: r.dni,
                "nombre":     lambda r: r.nombre,
                "apellido1":  lambda r: r.apellido1,
                "apellido2":  lambda r: r.apellido2,
                "ciclo":      lambda r: r.ciclo,
                "anio":       lambda r: r.anio,
                "turno":      lambda r: r.turno,
                "estado":     lambda r: (1 if r.en_revision else 0),
            }
            if self._sort_col in key_map:
                rows = sorted(rows, key=key_map[self._sort_col], reverse=self._sort_reverse)
        self._filtered_rows = rows
        self._rebuild_table()

    # ── Sorting ───────────────────────────────────────────────────

    def _on_sort(self, col: str):
        if self._sort_col == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_col = col
            self._sort_reverse = False
        self._update_header_texts()
        self._apply_filters()
        self.page.update()

    def _update_header_texts(self):
        c = self.colors
        for col, (txt, icon) in self._header_cells.items():
            is_active = self._sort_col == col
            txt.color = c["accent"] if is_active else c["text_dim"]
            icon.icon = self._sort_icon_name(col)
            icon.color = c["accent"] if is_active else c["text_dim"]

    # ── Table ─────────────────────────────────────────────────────

    def _rebuild_table(self):
        c = self.colors
        self._table_container.controls.clear()

        if not self._all_rows:
            self._count_text.value = "No hay expedientes en la carpeta de salida."
            self._table_container.controls.append(
                ft.Container(
                    padding=pad(all=24),
                    content=ft.Column([
                        ft.Icon(I.INBOX, color=c["text_dim"], size=40),
                        ft.Text("No se encontraron expedientes.", color=c["text_dim"], size=14),
                        ft.Text("Procesa PDFs primero.", color=c["text_dim"], size=12, italic=True),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                )
            )
        elif not self._filtered_rows:
            self._count_text.value = f"{len(self._filtered_rows)} de {len(self._all_rows)} expedientes"
            self._table_container.controls.append(
                ft.Container(padding=pad(all=20),
                    content=ft.Text("No hay expedientes con los filtros actuales.", color=c["text_dim"], italic=True))
            )
        else:
            self._count_text.value = f"{len(self._filtered_rows)} de {len(self._all_rows)} expedientes"
            for i, row in enumerate(self._filtered_rows):
                self._table_container.controls.append(self._build_row(row, i))

        try:
            self._table_container.update()
        except Exception:
            pass

    def _build_row(self, row: ExpedienteRow, idx: int) -> ft.Container:
        c = self.colors
        bg = c["surface"] if idx % 2 == 0 else c["card"]

        if row.en_revision:
            estado_text = "⚠ Revisión"
            estado_color = c["warning"]
            estado_bg    = c["warning_bg"]
        else:
            estado_text = "✅ Correcto"
            estado_color = c["success"]
            estado_bg    = c["success_bg"]

        estado_badge = ft.Container(
            content=ft.Text(estado_text, size=10, color=estado_color),
            bgcolor=estado_bg, border_radius=4, padding=pad(h=5, v=1),
            width=70,
        )

        motivos_tooltip = "\n".join(row.motivos) if row.motivos else ""

        def _open_pdf(e, r=row):
            if r.pdf_path:
                open_file(r.pdf_path)

        def _open_foto(e, r=row):
            if r.foto_path:
                open_file(r.foto_path)

        def _open_dir(e, r=row):
            open_folder(r.folder)

        def _view_json(e, r=row):
            self._show_json_dialog(r)

        def _delete(e, r=row):
            self._confirm_delete(r)

        def _review(e, r=row):
            self._open_review(r)

        return ft.Container(
            bgcolor=bg, padding=pad(h=10, v=4),
            border=border_all(1, c["border"]),
            content=ft.Row([
                ft.Text(row.expediente, size=11, color=c["text"], width=70,  no_wrap=True, tooltip=row.expediente),
                ft.Text(row.dni,        size=11, color=c["text"], width=100, no_wrap=True, tooltip=row.dni),
                ft.Text(row.nombre,     size=11, color=c["text"], width=85,  no_wrap=True, tooltip=row.nombre),
                ft.Text(row.apellido1,  size=11, color=c["text"], width=85,  no_wrap=True, tooltip=row.apellido1),
                ft.Text(row.apellido2,  size=11, color=c["text_muted"], width=70, no_wrap=True, tooltip=row.apellido2),
                ft.Text(row.ciclo,      size=11, color=c["text"], width=50,  no_wrap=True),
                ft.Text(row.anio,       size=11, color=c["text"], width=45,  no_wrap=True),
                ft.Text(row.turno,      size=11, color=c["text"], width=80,  no_wrap=True),
                ft.Container(content=estado_badge, tooltip=motivos_tooltip, width=75),
                ft.Container(expand=True),
                ft.Row([
                    action_icon_btn(
                        icon=I.PICTURE_AS_PDF,
                        icon_color=c["accent"] if row.pdf_path else c["text_dim"],
                        tooltip="Abrir PDF" if row.pdf_path else "PDF no encontrado",
                        on_click=_open_pdf,
                        disabled=not row.pdf_path,
                        hover_color=c["hover"],
                    ),
                    action_icon_btn(
                        icon=I.DATA_OBJECT,
                        icon_color=c["accent"],
                        tooltip="Ver datos JSON",
                        on_click=_view_json,
                        hover_color=c["hover"],
                    ),
                    action_icon_btn(
                        icon=I.PORTRAIT,
                        icon_color=c["accent"] if row.foto_path else c["text_dim"],
                        tooltip="Ver foto" if row.foto_path else "Foto no encontrada",
                        on_click=_open_foto,
                        disabled=not row.foto_path,
                        hover_color=c["hover"],
                    ),
                    action_icon_btn(
                        icon=I.FOLDER_OPEN,
                        icon_color=c["text_muted"],
                        tooltip="Abrir carpeta",
                        on_click=_open_dir,
                        hover_color=c["hover"],
                    ),
                    action_icon_btn(
                        icon=I.RATE_REVIEW,
                        icon_color=c["accent"],
                        tooltip="Revisar y editar expediente",
                        on_click=_review,
                        hover_color=c["hover"],
                    ),
                    action_icon_btn(
                        icon=I.DELETE_OUTLINE,
                        icon_color=c["error"],
                        tooltip="Mover a la papelera",
                        on_click=_delete,
                        hover_color=c["error_bg"],
                    ),
                ], spacing=0),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

    # ── Review dialog ─────────────────────────────────────────────

    def _open_review(self, row):
        from gui.views.review_dialog import ReviewDialog
        dlg = ReviewDialog(
            page=self.page,
            row=row,
            app_cfg=self.app.cfg,
            on_saved=self.refresh,
        )
        dlg.open()

    # ── Trash ─────────────────────────────────────────────────────

    def _update_trash_btn(self):
        out_dir = self.app.cfg.get("output_dir", "")
        if not out_dir:
            self._trash_btn_wrapper.visible = False
            try:
                self._trash_btn_wrapper.update()
            except Exception:
                pass
            return
        c = self.colors
        count = _count_trash(out_dir)
        self._trash_btn_wrapper.visible = True
        empty = count == 0
        self._trash_btn.disabled = empty
        if empty:
            label = "Papelera vacía"
            col   = c["text_dim"]
            bside = ft.BorderSide(1, c["border"])
        elif count == -1:
            label = "Vaciar papelera"
            col   = c["accent"]
            bside = ft.BorderSide(1, c["accent"])
        else:
            label = f"Vaciar papelera ({count})"
            col   = c["accent"]
            bside = ft.BorderSide(1, c["accent"])
        self._trash_label.value = label
        self._trash_label.color = col
        self._trash_icon.color  = col
        self._trash_btn.style = ft.ButtonStyle(color=col, side=bside)
        self._trash_btn_wrapper.mouse_cursor = MC.FORBIDDEN if empty else MC.CLICK
        self._open_trash_btn.disabled   = empty
        self._open_trash_btn.icon_color = c["text_dim"] if empty else c["accent"]
        self._open_trash_wrapper.mouse_cursor = MC.FORBIDDEN if empty else MC.CLICK
        try:
            self._trash_label.update()
            self._trash_icon.update()
            self._trash_btn.update()
            self._trash_btn_wrapper.update()
            self._open_trash_btn.update()
            self._open_trash_wrapper.update()
        except Exception:
            pass

    def _on_trash_hover(self, e):
        if self._trash_btn.disabled:
            return
        c = self.colors
        is_hov = e.data == "true"
        col = c["accent_hover"] if is_hov else c["accent"]
        self._trash_label.color = col
        self._trash_icon.color  = col
        self._trash_btn.style = ft.ButtonStyle(
            color=col,
            side=ft.BorderSide(2, col) if is_hov else ft.BorderSide(1, col),
        )
        self._trash_label.update()
        self._trash_icon.update()
        self._trash_btn.update()

    def _open_trash_folder(self, _e):
        out_dir = self.app.cfg.get("output_dir", "")
        td = _trash_dir(out_dir)
        if td.exists():
            open_folder(str(td))

    def _confirm_delete(self, row: ExpedienteRow):
        c = self.colors

        def _do_move(e):
            dlg_close(self.page, dlg)
            out_dir = self.app.cfg.get("output_dir", "")
            base = Path(out_dir)
            td = _trash_dir(out_dir)
            # Preservar jerarquía relativa dentro de _borrados para evitar colisiones
            try:
                relative = row.folder.relative_to(base)
                dest = td / relative
            except ValueError:
                dest = td / row.folder.name
            if dest.exists():
                import time as _time
                dest = dest.parent / f"{dest.name}_{int(_time.time())}"

            # Read JSON BEFORE moving — the file is gone after shutil.move
            input_dir = self.app.cfg.get("input_dir", "")
            pdf_orig = ""
            if input_dir and row.json_path:
                try:
                    import json as _json
                    data = _json.loads(row.json_path.read_text(encoding="utf-8"))
                    pdf_orig = data.get("metadata", {}).get("pdf_original", "")
                except Exception:
                    pdf_orig = ""

            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(row.folder), str(dest))
            # Limpiar carpetas vacías en output tras el move
            from modules.output_structure import cleanup_empty_dirs
            cleanup_empty_dirs(row.folder.parent, base)

            # Strip processed prefix from source PDF so it can be re-processed
            if pdf_orig:
                prefix = self.app.cfg.get("processed_prefix", "_!_")
                marked = Path(input_dir) / f"{prefix}{pdf_orig}"
                plain  = Path(input_dir) / pdf_orig
                if marked.exists() and not plain.exists():
                    try:
                        marked.rename(plain)
                    except Exception:
                        pass

            self.refresh()
            # Notify both Inicio views so they rebuild their output index
            if self.app._inicio_simple_view is not None:
                self.app._inicio_simple_view._scan_pdfs()
            if self.app._avanzada_view is not None:
                self.app._avanzada_view._scan_pdfs()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(I.DELETE_OUTLINE, color=c["error"], size=20),
                ft.Container(width=8),
                ft.Text("¿Mover a la papelera?", color=c["text"]),
            ]),
            content=ft.Column([
                ft.Text(
                    "Se moverá a la papelera el registro completo de:",
                    color=c["text_muted"], size=13,
                ),
                ft.Container(height=6),
                ft.Text(
                    row.folder.name,
                    color=c["text"], size=12, font_family="monospace",
                    selectable=True,
                ),
                ft.Container(height=6),
                ft.Text(
                    "Podrás recuperarlo manualmente antes de vaciar la papelera.",
                    color=c["text_dim"], size=11, italic=True,
                ),
            ], tight=True, spacing=0),
            bgcolor=c["surface"],
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: dlg_close(self.page, dlg)),
                ft.ElevatedButton(
                    "Mover a papelera", icon=I.DELETE_OUTLINE,
                    bgcolor=c["error"], color="#ffffff",
                    on_click=_do_move,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, dlg)

    def _empty_trash(self, _e):
        c = self.colors
        out_dir = self.app.cfg.get("output_dir", "")
        count = _count_trash(out_dir)
        td = _trash_dir(out_dir)

        def _do_empty(e):
            dlg_close(self.page, dlg)
            try:
                shutil.rmtree(str(td))
            except Exception:
                pass
            self._update_trash_btn()
            self.page.update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(I.DELETE_FOREVER, color=c["error"], size=20),
                ft.Container(width=8),
                ft.Text("¿Vaciar la papelera?", color=c["text"]),
            ]),
            content=ft.Text(
                (f"Se eliminarán permanentemente {count} expediente(s).\n"
                 if count > 0 else "Se eliminará el contenido de la papelera.\n") +
                "Esta acción no se puede deshacer.",
                color=c["text_muted"], size=13,
            ),
            bgcolor=c["surface"],
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: dlg_close(self.page, dlg)),
                ft.ElevatedButton(
                    "Eliminar definitivamente", icon=I.DELETE_FOREVER,
                    bgcolor=c["error"], color="#ffffff",
                    on_click=_do_empty,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, dlg)

    # ── JSON dialog ───────────────────────────────────────────────

    def _show_json_dialog(self, row: ExpedienteRow):
        c = self.colors
        try:
            raw = json.loads(row.json_path.read_text(encoding="utf-8"))
            content_text = json.dumps(raw, indent=2, ensure_ascii=False)
        except Exception as ex:
            content_text = f"Error leyendo JSON: {ex}"

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(I.DATA_OBJECT, color=c["accent"], size=20),
                ft.Container(width=8),
                ft.Text(f"datos.json — {row.folder.name}", color=c["text"], size=14),
            ]),
            content=ft.Container(
                width=560, height=420,
                bgcolor=c["card"], border_radius=8,
                content=ft.ListView(
                    expand=True, spacing=0, padding=pad(all=12),
                    controls=[
                        ft.Text(
                            content_text, size=11, color=c["text_muted"],
                            font_family="monospace", selectable=True,
                        )
                    ],
                ),
            ),
            bgcolor=c["surface"],
            actions=[
                ft.TextButton("Cerrar", on_click=lambda e: dlg_close(self.page, dlg)),
                ft.OutlinedButton(
                    "Abrir archivo", icon=I.OPEN_IN_NEW,
                    style=ft.ButtonStyle(color=c["accent"]),
                    on_click=lambda e: (dlg_close(self.page, dlg), open_file(row.json_path)),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, dlg)
