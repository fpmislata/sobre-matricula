import flet as ft
from gui.theme import get_colors
from gui.config_manager import load_config, save_config
from gui.flet_compat import I, MC, pad, mar, border_all, border_only, dlg_open, dlg_close, accent_btn
from gui.processing_manager import ProcessingManager
from gui.views.inicio import InicioView
from gui.views.inicio_simple import InicioSimpleView
from gui.views.configuracion import ConfiguracionView
from gui.views.logs import LogsView
from gui.views.output import OutputView


class DNIApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.cfg = load_config()
        self._current_nav = "inicio_simple"
        self._nav_btns: dict[str, ft.Container] = {}
        self.processing_mgr = ProcessingManager(self)
        self._inicio_simple_view: InicioSimpleView | None = None
        self._avanzada_view: InicioView | None = None
        self._config_view: ConfiguracionView | None = None
        self._logs_view: LogsView | None = None
        self._output_view: OutputView | None = None
        self.content_container: ft.Container = ft.Container(expand=True)

    def build(self):
        c = get_colors(self.cfg.get("theme", "dark"))
        self.page.title = "Expediente Extractor"
        self.page.theme_mode = (
            ft.ThemeMode.DARK if self.cfg.get("theme", "dark") == "dark" else ft.ThemeMode.LIGHT
        )
        self.page.window.maximized = True
        self.page.bgcolor = c["bg"]
        self.page.padding = 0

        self.page.add(
            ft.Row(
                [self._build_sidebar(), self.content_container],
                expand=True, spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        )
        self.navigate("inicio_simple")

    # ── Sidebar ───────────────────────────────────────────────────

    def _build_sidebar(self) -> ft.Container:
        c = get_colors(self.cfg.get("theme", "dark"))

        logo = ft.Container(
            padding=pad(h=16, v=20),
            content=ft.Column([
                ft.Icon(I.DOCUMENT_SCANNER, color=c["accent"], size=36),
                ft.Container(height=4),
                ft.Text(
                    "Expediente\nExtractor", size=13,
                    weight=ft.FontWeight.BOLD, color=c["text"],
                    text_align=ft.TextAlign.CENTER,
                ),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
        )

        nav_items = [
            ("inicio_simple", I.HOME,        "Inicio"),
            ("avanzada",      I.LAYERS,      "Avanzada"),
            ("output",        I.TABLE_CHART, "Expedientes"),
            ("logs",          I.DESCRIPTION, "Logs"),
            ("config",        I.SETTINGS,    "Configuración"),
        ]
        nav_controls = []
        for nav_id, icon, label in nav_items:
            btn = self._nav_button(nav_id, icon, label)
            self._nav_btns[nav_id] = btn
            nav_controls.append(btn)
        nav_list = ft.Column(nav_controls, spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)

        theme_toggle = ft.Container(
            padding=pad(h=14, v=10),
            content=ft.Row([
                ft.Icon(I.DARK_MODE, size=15, color=c["text_muted"]),
                ft.Switch(
                    value=self.cfg.get("theme", "dark") == "light",
                    active_color=c["accent"],
                    on_change=self._toggle_theme,
                    height=28,
                ),
                ft.Icon(I.LIGHT_MODE, size=15, color=c["text_muted"]),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        )

        return ft.Container(
            width=185, bgcolor=c["sidebar_bg"],
            border=border_only(right=ft.BorderSide(1, c["border"])),
            content=ft.Column([
                logo,
                ft.Divider(height=1, color=c["border"], thickness=1),
                ft.Container(height=8),
                nav_list,
                ft.Divider(height=1, color=c["border"], thickness=1),
                theme_toggle,
            ], spacing=0, expand=True),
        )

    def _nav_button(self, nav_id: str, icon, label: str) -> ft.GestureDetector:
        c = get_colors(self.cfg.get("theme", "dark"))
        is_sel = nav_id == self._current_nav
        inner = ft.Container(
            data=nav_id, margin=mar(h=8), padding=pad(h=12, v=11),
            border_radius=8, bgcolor=c["accent_bg"] if is_sel else "transparent",
            ink=True, on_click=lambda e, nid=nav_id: self.navigate(nid),
            content=ft.Row([
                ft.Icon(icon, size=18, color=c["accent"] if is_sel else c["text_muted"]),
                ft.Text(
                    label, size=13,
                    color=c["accent_text"] if is_sel else c["text_muted"],
                    weight=ft.FontWeight.W_600 if is_sel else ft.FontWeight.NORMAL,
                ),
            ], spacing=10),
        )

        def _hover(e, btn=inner, nid=nav_id, theme_c=c):
            active = self._current_nav == nid
            base   = theme_c["accent_bg"] if active else "transparent"
            hovered = theme_c["accent_bg"] if active else theme_c["hover"]
            btn.bgcolor = hovered if e.data == "true" else base
            btn.update()

        return ft.GestureDetector(mouse_cursor=MC.CLICK, content=inner, on_hover=_hover)

    # ── Navigation ────────────────────────────────────────────────

    def navigate(self, nav_id: str):
        if (self._current_nav == "config"
                and nav_id != "config"
                and self._config_view
                and self._config_view._dirty):
            self._show_unsaved_dialog(nav_id)
            return
        self._do_navigate(nav_id)

    def _do_navigate(self, nav_id: str):
        self._current_nav = nav_id
        c = get_colors(self.cfg.get("theme", "dark"))
        first_time = False

        for nid, btn in self._nav_btns.items():
            sel = nid == nav_id
            inner = btn.content
            inner.bgcolor = c["accent_bg"] if sel else "transparent"
            row = inner.content
            row.controls[0].color = c["accent"] if sel else c["text_muted"]
            row.controls[1].color = c["accent_text"] if sel else c["text_muted"]
            row.controls[1].weight = ft.FontWeight.W_600 if sel else ft.FontWeight.NORMAL

        if nav_id == "inicio_simple":
            first_time = not self._inicio_simple_view
            if not self._inicio_simple_view:
                self._inicio_simple_view = InicioSimpleView(self)
            else:
                self._inicio_simple_view.refresh()
            self.content_container.content = self._inicio_simple_view.root

        elif nav_id == "avanzada":
            first_time = not self._avanzada_view
            if not self._avanzada_view:
                self._avanzada_view = InicioView(self)
            else:
                self._avanzada_view.refresh()
            self.content_container.content = self._avanzada_view.root

        elif nav_id == "config":
            if not self._config_view:
                self._config_view = ConfiguracionView(self)
            self.content_container.content = self._config_view.root

        elif nav_id == "logs":
            if not self._logs_view:
                self._logs_view = LogsView(self)
            self._logs_view.refresh()
            self.content_container.content = self._logs_view.root

        elif nav_id == "output":
            if not self._output_view:
                self._output_view = OutputView(self)
            self._output_view.refresh()
            self.content_container.content = self._output_view.root

        self.page.update()
        if nav_id == "inicio_simple" and first_time:
            self._inicio_simple_view.check_folders_on_startup()

    # ── Unsaved changes dialog ────────────────────────────────────

    def _show_unsaved_dialog(self, target_nav: str):
        c = get_colors(self.cfg.get("theme", "dark"))

        def _save_and_go(e):
            dlg_close(self.page, dlg)
            if self._config_view:
                self._config_view._on_save(None)
            self._do_navigate(target_nav)

        def _discard_and_go(e):
            dlg_close(self.page, dlg)
            if self._config_view:
                self._config_view._dirty = False
            self._do_navigate(target_nav)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cambios sin guardar", color=c["text"]),
            content=ft.Text(
                "Hay cambios sin guardar en la configuración.\n"
                "Debes guardarlos para que tengan efecto.",
                color=c["text_muted"], size=13,
            ),
            bgcolor=c["surface"],
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: dlg_close(self.page, dlg)),
                ft.TextButton(
                    "Descartar", on_click=_discard_and_go,
                    style=ft.ButtonStyle(color=c["error"]),
                ),
                accent_btn("Guardar", icon=I.SAVE, on_click=_save_and_go, colors=c),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, dlg)

    # ── Theme toggle ──────────────────────────────────────────────

    def _toggle_theme(self, e):
        new_theme = "light" if getattr(e, "data", None) == "true" or getattr(e.control, "value", False) else "dark"
        self.cfg["theme"] = new_theme
        save_config(self.cfg)

        self.page.theme_mode = ft.ThemeMode.LIGHT if new_theme == "light" else ft.ThemeMode.DARK

        self._inicio_simple_view = None
        self._avanzada_view      = None
        self._config_view        = None
        self._logs_view          = None
        self._output_view        = None
        self._nav_btns.clear()

        self.page.controls.clear()
        c = get_colors(new_theme)
        self.page.bgcolor = c["bg"]
        self.content_container = ft.Container(expand=True)
        self.page.add(
            ft.Row(
                [self._build_sidebar(), self.content_container],
                expand=True, spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        )
        self.navigate(self._current_nav)
