"""Modal dialog for manual review and editing of an expediente."""

import json
import flet as ft
from pathlib import Path

from gui.theme import get_colors
from gui.flet_compat import (
    I, MC, pad, border_all,
    dlg_open, dlg_close, snack_open, action_icon_btn, accent_btn,
)
from gui import review_manager as rm
from gui.system_utils import open_file


_ASISTENCIA_OPTIONS = ["presencial", "semipresencial", "libre", "parcial"]


class ReviewDialog:
    """
    Modal dialog for reviewing and editing an expediente.

    Usage:
        dlg = ReviewDialog(page, row, app_cfg, on_saved=output_view.refresh)
        dlg.open()
    """

    def __init__(self, page: ft.Page, row, app_cfg: dict, on_saved):
        self.page     = page
        self.row      = row
        self.app_cfg  = app_cfg
        self.on_saved = on_saved
        self.c        = get_colors(app_cfg.get("theme", "dark"))
        self._new_photo_path: str | None = None
        self._dlg: ft.AlertDialog | None = None

        try:
            self._data = json.loads(row.json_path.read_text(encoding="utf-8"))
        except Exception:
            self._data = {}

        self._build_controls()

    # ── Control construction ───────────────────────────────────────────────────

    def _build_controls(self):
        c      = self.c
        data   = self._data
        ciclos = self.app_cfg.get("ciclos", {})
        doc    = data.get("documento") or {}
        ciclo  = data.get("ciclo") or {}
        curso  = data.get("curso") or {}
        meta   = data.get("metadata") or {}

        tf = dict(
            bgcolor=c["input_bg"],
            border_color=c["border"],
            color=c["text"],
            focused_border_color=c["accent"],
            label_style=ft.TextStyle(color=c["text_dim"]),
            border_radius=8,
            text_size=13,
            content_padding=pad(h=10, v=8),
        )

        self._tf_expediente = ft.TextField(
            label="Expediente",
            value=str(data.get("expediente") or ""),
            **tf,
        )
        self._tf_dni = ft.TextField(
            label="DNI / NIE / Pasaporte",
            value=str(doc.get("numero_verificado") or ""),
            capitalization=ft.TextCapitalization.CHARACTERS,
            **tf,
        )
        self._tf_nombre   = ft.TextField(label="Nombre",             value=str(data.get("nombre")   or ""), **tf)
        self._tf_apellido1 = ft.TextField(label="Apellido 1",        value=str(data.get("apellido1") or ""), **tf)
        self._tf_apellido2 = ft.TextField(label="Apellido 2 (opcional)", value=str(data.get("apellido2") or ""), **tf)
        self._tf_anio_ini  = ft.TextField(label="Inicio", value=str(curso.get("inicio") or ""), width=110, **tf)
        self._tf_anio_fin  = ft.TextField(label="Fin",    value=str(curso.get("fin")    or ""), width=110, **tf)

        # Ciclo dropdown
        ciclo_cod = ciclo.get("codigo", "")
        self._dd_ciclo = ft.Dropdown(
            label="Ciclo",
            value=ciclo_cod if ciclo_cod in ciclos else None,
            options=[
                ft.dropdown.Option(key=k, text=f"{k} — {v['nombre']}")
                for k, v in sorted(ciclos.items())
            ],
            bgcolor=c["input_bg"],
            border_color=c["border"],
            color=c["text"],
            label_style=ft.TextStyle(color=c["text_dim"]),
            focused_border_color=c["accent"],
            border_radius=8,
            content_padding=pad(h=10, v=6),
            on_select=self._on_ciclo_change,
        )
        self._ciclo_info = ft.Text("", size=11, color=c["text_muted"], italic=True)
        self._update_ciclo_info(ciclo_cod)

        # Asistencia dropdown
        asistencia_val = str(data.get("tipo_asistencia") or "presencial")
        self._dd_asistencia = ft.Dropdown(
            label="Tipo de asistencia",
            value=asistencia_val if asistencia_val in _ASISTENCIA_OPTIONS else "presencial",
            options=[ft.dropdown.Option(k, k.capitalize()) for k in _ASISTENCIA_OPTIONS],
            bgcolor=c["input_bg"],
            border_color=c["border"],
            color=c["text"],
            label_style=ft.TextStyle(color=c["text_dim"]),
            focused_border_color=c["accent"],
            border_radius=8,
            content_padding=pad(h=10, v=6),
        )

        # Status badge
        en_rev  = meta.get("en_revision", getattr(self.row, "en_revision", False))
        motivos = meta.get("motivos_revision") or getattr(self.row, "motivos", []) or []
        self._status_icon = ft.Icon(
            I.WARNING_AMBER_ROUNDED if en_rev else I.CHECK_CIRCLE_OUTLINE,
            color=c["warning"] if en_rev else c["success"],
            size=16,
        )
        self._status_text = ft.Text(
            "⚠ En revisión" if en_rev else "✅ Correcto",
            color=c["warning"] if en_rev else c["success"],
            size=12,
            weight=ft.FontWeight.W_600,
        )
        self._motivos_text = ft.Text(
            ("Motivos: " + " | ".join(motivos)) if motivos else "",
            size=11, color=c["text_dim"], italic=True,
        )
        self._error_text = ft.Text("", size=12, color=c["error"])

        # Photo area
        foto_path = getattr(self.row, "foto_path", None)
        self._photo_area = ft.Container(
            width=200, height=200,
            border_radius=8,
            content=self._make_photo_content(str(foto_path) if foto_path else None),
        )

        # Page-1 preview
        folder   = getattr(self.row, "folder", Path())
        page1    = folder / "debug" / "pagina_1.jpg"
        self._page1_area = ft.Container(
            width=200, height=240,
            border_radius=8,
            content=self._make_page1_content(str(page1) if page1.exists() else None),
        )

    # ── Image helpers ──────────────────────────────────────────────────────────

    def _make_photo_content(self, path: str | None) -> ft.Control:
        c = self.c
        if path and Path(path).exists():
            return ft.Image(src=path, width=200, height=200,
                            fit=ft.BoxFit.CONTAIN, border_radius=8)
        return ft.Container(
            width=200, height=200,
            bgcolor=c["card"], border_radius=8,
            border=border_all(1, c["border"]),
            content=ft.Column(
                [ft.Icon(I.PORTRAIT, color=c["text_dim"], size=36),
                 ft.Text("Sin foto", color=c["text_dim"], size=11)],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=4,
            ),
        )

    def _make_page1_content(self, path: str | None) -> ft.Control:
        c = self.c
        if path:
            return ft.Image(src=path, width=200, height=240,
                            fit=ft.BoxFit.CONTAIN, border_radius=8)
        return ft.Container(
            width=200, height=240,
            bgcolor=c["card"], border_radius=8,
            border=border_all(1, c["border"]),
            content=ft.Column(
                [ft.Icon(I.DESCRIPTION, color=c["text_dim"], size=36),
                 ft.Text("Sin previsualización", color=c["text_dim"], size=11)],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=4,
            ),
        )

    # ── Event handlers ─────────────────────────────────────────────────────────

    def _update_ciclo_info(self, codigo: str):
        ciclos = self.app_cfg.get("ciclos", {})
        if codigo and codigo in ciclos:
            info = ciclos[codigo]
            self._ciclo_info.value = f"{info['nombre']}  ·  Grado {info.get('grado', '')}"
        else:
            self._ciclo_info.value = ""

    def _on_ciclo_change(self, e):
        self._update_ciclo_info(self._dd_ciclo.value or "")
        self._ciclo_info.update()

    async def _pick_photo(self, e):
        result = await ft.FilePicker().pick_files(
            allow_multiple=False,
            dialog_title="Seleccionar foto",
            allowed_extensions=["jpg", "jpeg", "png", "bmp", "webp"],
        )
        if result and result.files:
            self._new_photo_path = result.files[0].path
            self._photo_area.content = ft.Image(
                src=self._new_photo_path,
                width=200, height=200,
                fit=ft.BoxFit.CONTAIN,
                border_radius=8,
            )
            self._photo_area.update()

    def _collect_form_data(self) -> dict:
        ciclos    = self.app_cfg.get("ciclos", {})
        ciclo_cod = (self._dd_ciclo.value or "").strip()
        ciclo_info = ciclos.get(ciclo_cod, {})
        orig_ciclo = self._data.get("ciclo") or {}
        return {
            "expediente": (self._tf_expediente.value or "").strip(),
            "nombre":     (self._tf_nombre.value or "").strip() or None,
            "apellido1":  (self._tf_apellido1.value or "").strip() or None,
            "apellido2":  (self._tf_apellido2.value or "").strip() or None,
            "tipo_asistencia": self._dd_asistencia.value or "presencial",
            "ciclo": {
                "codigo":          ciclo_cod,
                "nombre_completo": ciclo_info.get("nombre", ""),
                "grado":           ciclo_info.get("grado", ""),
                "texto_original":  orig_ciclo.get("texto_original", ciclo_cod),
            },
            "curso": {
                "inicio": (self._tf_anio_ini.value or "").strip() or None,
                "fin":    (self._tf_anio_fin.value or "").strip() or None,
            },
            "documento": {
                "numero_verificado": (self._tf_dni.value or "").strip().upper(),
            },
        }

    def _on_save(self, e):
        ciclos    = self.app_cfg.get("ciclos", {})
        form_data = self._collect_form_data()
        errors    = rm.validate_review_data(form_data, ciclos)
        if errors:
            self._error_text.value = " | ".join(errors)
            self._error_text.update()
            return
        self._error_text.value = ""
        self._do_save(form_data, force=False)

    def _do_save(self, form_data: dict, force: bool):
        c = self.c
        code, payload = rm.save_review_changes(
            current_folder=self.row.folder,
            json_path=self.row.json_path,
            new_data=form_data,
            new_photo_path=self._new_photo_path,
            app_cfg=self.app_cfg,
            force_overwrite=force,
        )
        if code == "ok":
            dlg_close(self.page)
            snack_open(self.page, "Cambios guardados correctamente", c["success"])
            self.on_saved()
        elif code == "conflict":
            self._show_conflict_dialog(payload, form_data)
        else:
            self._error_text.value = f"Error: {payload}"
            self._error_text.update()

    # ── Conflict dialog ────────────────────────────────────────────────────────

    def _show_conflict_dialog(self, conflict: dict, form_data: dict):
        c      = self.c
        new_s  = conflict["new_summary"]
        exist_s = conflict["existing_summary"]

        _ROWS = [
            ("Expediente", "expediente"),
            ("DNI",        "documento"),
            ("Nombre",     "nombre"),
            ("Apellido 1", "apellido1"),
            ("Apellido 2", "apellido2"),
            ("Ciclo",      "ciclo"),
            ("Asistencia", "asistencia"),
            ("Año inicio", "curso_inicio"),
            ("Año fin",    "curso_fin"),
        ]

        def _field_row(label: str, key: str) -> ft.Row:
            nv   = new_s.get(key, "")
            ev   = exist_s.get(key, "")
            diff = nv != ev
            return ft.Row([
                ft.Text(label + ":", size=11, color=c["text_dim"], width=80, no_wrap=True),
                ft.Container(
                    width=155,
                    bgcolor=c["warning_bg"] if diff else None,
                    border_radius=3,
                    padding=pad(h=4, v=1) if diff else None,
                    content=ft.Text(
                        nv or "—", size=11,
                        color=c["warning"] if diff else c["text"],
                        no_wrap=True,
                    ),
                ),
                ft.Container(
                    width=155,
                    bgcolor=c["error_bg"] if diff else None,
                    border_radius=3,
                    padding=pad(h=4, v=1) if diff else None,
                    content=ft.Text(
                        ev or "—", size=11,
                        color=c["error"] if diff else c["text_muted"],
                        no_wrap=True,
                    ),
                ),
            ], spacing=6)

        def _on_force_save(e):
            dlg_close(self.page)        # pop conflict dialog
            self._do_save(form_data, force=True)

        conflict_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(I.WARNING_AMBER_ROUNDED, color=c["warning"], size=20),
                ft.Container(width=8),
                ft.Text("Conflicto: ya existe este expediente", color=c["text"], size=14),
            ]),
            content=ft.Container(
                width=530,
                content=ft.Column(
                    [
                        ft.Text(
                            f"Ya existe la carpeta '{conflict['existing_folder'].name}'.",
                            color=c["text_muted"], size=12,
                        ),
                        ft.Container(height=6),
                        ft.Row([
                            ft.Text("Campo",    size=11, weight=ft.FontWeight.W_700, color=c["text_dim"], width=80),
                            ft.Text("NUEVO",    size=11, weight=ft.FontWeight.W_700, color=c["accent"], width=155),
                            ft.Text("EXISTENTE", size=11, weight=ft.FontWeight.W_700, color=c["text_muted"], width=155),
                        ], spacing=6),
                        ft.Divider(color=c["border"], height=1),
                        *[_field_row(label, key) for label, key in _ROWS],
                        ft.Container(height=6),
                        ft.Container(
                            bgcolor=c["warning_bg"], border_radius=6,
                            padding=pad(all=8),
                            content=ft.Text(
                                "Al sobrescribir, el expediente existente se moverá a la papelera.",
                                size=11, color=c["warning"],
                            ),
                        ),
                    ],
                    spacing=4, tight=True,
                ),
            ),
            bgcolor=c["surface"],
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: dlg_close(self.page)),
                ft.ElevatedButton(
                    "Sobrescribir", icon=I.DELETE_SWEEP,
                    bgcolor=c["warning"], color="#ffffff",
                    on_click=_on_force_save,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, conflict_dlg)

    # ── Build panels ───────────────────────────────────────────────────────────

    def _build_form(self) -> ft.Container:
        c = self.c
        return ft.Container(
            expand=True,
            padding=pad(right=12),
            content=ft.Column(
                [
                    ft.Text("Datos del expediente", size=13,
                            weight=ft.FontWeight.W_600, color=c["text"]),
                    self._tf_expediente,
                    self._tf_dni,
                    ft.Divider(color=c["border"], height=1),
                    self._tf_nombre,
                    self._tf_apellido1,
                    self._tf_apellido2,
                    ft.Divider(color=c["border"], height=1),
                    self._dd_ciclo,
                    self._ciclo_info,
                    self._dd_asistencia,
                    ft.Row(
                        [
                            ft.Text("Curso:", size=12, color=c["text_muted"]),
                            self._tf_anio_ini,
                            ft.Text("→", size=14, color=c["text_dim"]),
                            self._tf_anio_fin,
                        ],
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(color=c["border"], height=1),
                    ft.Row([self._status_icon, self._status_text], spacing=6),
                    self._motivos_text,
                    self._error_text,
                ],
                spacing=8,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    def _build_preview(self) -> ft.Container:
        c = self.c
        photo_btn = ft.ElevatedButton(
            "Añadir / Reemplazar foto",
            icon=I.ADD_PHOTO_ALTERNATE,
            style=ft.ButtonStyle(
                color=c["text"],
                bgcolor=c["card"],
                side=ft.BorderSide(1, c["border"]),
            ),
            on_click=self._pick_photo,
        )
        return ft.Container(
            width=235,
            padding=pad(left=12),
            content=ft.Column(
                [
                    ft.Text("Foto", size=11, weight=ft.FontWeight.W_600,
                            color=c["text_muted"]),
                    self._photo_area,
                    photo_btn,
                    ft.Container(height=8),
                    ft.Text("Página 1 del PDF", size=11, weight=ft.FontWeight.W_600,
                            color=c["text_muted"]),
                    self._page1_area,
                ],
                spacing=6,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    # ── Public entry point ────────────────────────────────────────────────────

    def open(self):
        c      = self.c
        meta   = self._data.get("metadata") or {}
        en_rev = meta.get("en_revision", getattr(self.row, "en_revision", False))

        folder    = getattr(self.row, "folder", Path())
        apellido1 = getattr(self.row, "apellido1", "")
        nombre    = getattr(self.row, "nombre", "")
        title_name = f"{apellido1}, {nombre}" if apellido1 else folder.name

        pdf_path = getattr(self.row, "pdf_path", None)
        has_pdf  = pdf_path is not None and Path(str(pdf_path)).exists()
        pdf_btn  = ft.IconButton(
            icon=I.PICTURE_AS_PDF,
            icon_color=c["accent"] if has_pdf else c["text_dim"],
            tooltip="Abrir PDF" if has_pdf else "PDF no encontrado",
            disabled=not has_pdf,
            on_click=lambda e: open_file(str(pdf_path)),
        )

        self._dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([
                ft.Icon(I.RATE_REVIEW, color=c["accent"], size=20),
                ft.Container(width=8),
                ft.Text(f"Revisar — {title_name}", color=c["text"], size=14),
                ft.Container(expand=True),
                pdf_btn,
                ft.Container(width=4),
                ft.Container(
                    content=ft.Text(
                        "⚠ En revisión" if en_rev else "✅ Correcto",
                        size=11,
                        color=c["warning"] if en_rev else c["success"],
                    ),
                    bgcolor=c["warning_bg"] if en_rev else c["success_bg"],
                    border_radius=4,
                    padding=pad(h=8, v=2),
                ),
            ]),
            content=ft.Container(
                width=720,
                height=560,
                content=ft.Row(
                    [
                        self._build_form(),
                        ft.VerticalDivider(color=c["border"], width=1),
                        self._build_preview(),
                    ],
                    spacing=0,
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ),
            bgcolor=c["surface"],
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: dlg_close(self.page)),
                accent_btn("Guardar", icon=I.SAVE, on_click=self._on_save, colors=c),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, self._dlg)
