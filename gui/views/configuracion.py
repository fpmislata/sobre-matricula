import hashlib
import re as _re
import time
import threading
import flet as ft
from pathlib import Path
from gui.theme import get_colors
from gui.config_manager import (
    save_config, save_default_config, get_defaults, load_config, DEFAULTS,
)
from gui.flet_compat import I, MC, pad, mar, border_all, tabs_control, snack_open, dlg_open, dlg_close, safe_update, accent_btn
from modules.output_structure import (
    validate_structure_template,
    render_structure_preview,
    reorganize_output,
)

_STRUCTURE_PREVIEW_SAMPLES = [
    {
        "ciclo": {"grado": "superior", "codigo": "DAW",
                  "nombre_completo": "Desarrollo de Aplicaciones Web"},
        "curso": {"inicio": "2025", "fin": "2026"}, "tipo_asistencia": "presencial",
        "nombre": "ANA", "apellido1": "MARTIN", "expediente": "16001",
        "documento": {"numero_verificado": "12345678Z"},
        "_preview_label": "ANA_MARTIN_RUIZ,ANA_E16001_P2526_M",
    },
    {
        "ciclo": {"grado": "superior", "codigo": "DAM",
                  "nombre_completo": "Desarrollo de Aplicaciones Multiplataforma"},
        "curso": {"inicio": "2025", "fin": "2026"}, "tipo_asistencia": "semipresencial",
        "nombre": "CARLOS", "apellido1": "LOPEZ", "expediente": "15234",
        "documento": {"numero_verificado": "87654321X"},
        "_preview_label": "CARLOS_LOPEZ,CARLOS_E15234_S2526_M",
    },
    {
        "ciclo": {"grado": "medio", "codigo": "SMR",
                  "nombre_completo": "Sistemas Microinformáticos y Redes"},
        "curso": {"inicio": "2024", "fin": "2025"}, "tipo_asistencia": "presencial",
        "nombre": "SARA", "apellido1": "EL", "expediente": "16100",
        "documento": {"numero_verificado": "99887766W"},
        "_preview_label": "SARA_EL_OUALI,SARA_E16100_P2425_M",
    },
]

_VALID_FIELDS = frozenset({
    "nombre", "apellido1", "apellido2", "expediente", "documento",
    "asistencia", "año_ini", "año_fin",
    "sufijo",  # kept for backwards-compat; no UI chip shown
})


def _validate_format(fmt: str) -> tuple[bool, str]:
    if not fmt.strip():
        return False, "El formato no puede estar vacío"
    tokens = _re.findall(r'\{([^}]+)\}', fmt)
    invalid = [t for t in tokens if t not in _VALID_FIELDS]
    if invalid:
        return False, "Campo(s) desconocido(s): " + ", ".join(f"{{{t}}}" for t in invalid)
    if "{expediente}" not in fmt:
        return False, "Debe incluir {expediente}"
    return True, "Formato válido"


def _apply_fmt(fmt: str, fields: dict) -> str:
    result = fmt
    for key, val in fields.items():
        if not val:
            result = _re.sub(r'[_,]?\{' + _re.escape(key) + r'\}', '', result)
        else:
            result = result.replace(f'{{{key}}}', val)
    result = _re.sub(r'_,', ',', result)
    result = _re.sub(r',_', ',', result)
    # Strip trailing separators; strip only leading commas (keep leading underscores)
    return result.rstrip('_,').lstrip(',')


def _preview_names(fmt: str) -> tuple[str, str]:
    base = {
        "nombre": "ANA", "apellido1": "MARTIN", "expediente": "16001",
        "documento": "87654321Z", "asistencia": "P",
        "año_ini": "25", "año_fin": "26", "sufijo": "_M",
    }
    with_ap2    = _apply_fmt(fmt, {**base, "apellido2": "RUIZ"})
    without_ap2 = _apply_fmt(fmt, {**base, "apellido2": ""})
    return with_ap2, without_ap2


def _card(content: ft.Control, colors: dict) -> ft.Container:
    return ft.Container(
        content=content, bgcolor=colors["card"], border_radius=10,
        border=border_all(1, colors["border"]), padding=pad(all=16), margin=mar(bottom=12),
    )


def _field_group(label: str, description: str, control: ft.Control, colors: dict) -> ft.Column:
    return ft.Column([
        ft.Text(label, size=13, weight=ft.FontWeight.W_600, color=colors["text"]),
        ft.Text(description, size=11, color=colors["text_dim"]),
        ft.Container(height=6),
        control,
    ], spacing=2)


def _textfield(value, colors: dict, password: bool = False, width=None) -> ft.TextField:
    return ft.TextField(
        value=str(value) if value is not None else "",
        password=password, can_reveal_password=password,
        bgcolor=colors["input_bg"], border_color=colors["border"],
        focused_border_color=colors["accent"], color=colors["text"],
        cursor_color=colors["accent"], border_radius=8,
        content_padding=pad(h=12, v=10), width=width,
    )


def _checkbox(label: str, value: bool, colors: dict) -> ft.Checkbox:
    return ft.Checkbox(
        label=label, value=value, active_color=colors["accent"],
        check_color=colors["bg"], label_style=ft.TextStyle(color=colors["text"], size=13),
    )


def _dropdown(value: str, options: list[str], colors: dict, width=None) -> ft.Dropdown:
    return ft.Dropdown(
        value=value, options=[ft.dropdown.Option(o) for o in options],
        bgcolor=colors["input_bg"], border_color=colors["border"],
        focused_border_color=colors["accent"], color=colors["text"],
        border_radius=8, content_padding=pad(h=12, v=8), width=width,
    )


def _md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()



class ConfiguracionView:
    def __init__(self, app, unlocked: bool = False):
        self.app = app
        self.page = app.page
        self.colors = get_colors(app.cfg.get("theme", "dark"))
        self._ciclo_rows: list[dict] = []
        self._dirty = False
        self._is_authenticated = unlocked
        self._locked = not unlocked
        self._has_reorganized_this_session = False  # True si reorganizó antes de guardar
        # Controles de estructura (inicializados en _build_structure_card y _tab_general)
        self._structure_field = None
        self._structure_status = None
        self._structure_preview = None
        self._reorg_btn = None
        self._skip_pending_cb = None
        self.root = self._build()

    # ── Dirty tracking ─────────────────────────────────────────────

    def _mark_dirty(self, _e=None):
        self._dirty = True

    # ── Build ─────────────────────────────────────────────────────

    def _build(self) -> ft.Control:
        c = self.colors
        cfg = self.app.cfg
        has_password = bool(cfg.get("config_password_hash"))

        # Lock button appearance
        if self._locked:
            lock_icon  = I.LOCK
            lock_color = c["error"]
            lock_tip   = (
                "Sin contraseña — pulsa para establecerla y acceder"
                if not has_password else
                "Configuración bloqueada — pulsa para desbloquear"
            )
        else:
            lock_icon  = I.LOCK_OPEN
            lock_color = c.get("success", "#4CAF50")
            lock_tip   = "Configuración desbloqueada — pulsa para bloquear"

        self._lock_btn = ft.IconButton(
            icon=lock_icon, icon_color=lock_color, tooltip=lock_tip,
            on_click=self._on_lock_click,
        )

        action_buttons = [
            ft.OutlinedButton(
                "Restaurar guardados", icon=I.HISTORY,
                style=ft.ButtonStyle(color=c["text_muted"]),
                tooltip="Recarga la configuración guardada, descartando los cambios actuales",
                on_click=self._on_restore_saved,
            ),
            ft.OutlinedButton(
                "Valores por defecto", icon=I.RESTORE,
                style=ft.ButtonStyle(color=c["text_muted"]),
                on_click=self._on_reset,
            ),
            ft.OutlinedButton(
                "Guardar como defaults", icon=I.BOOKMARK,
                style=ft.ButtonStyle(color=c["text_muted"]),
                tooltip="Guarda la configuración actual como config_default.json (base para 'Valores por defecto')",
                on_click=self._on_save_as_default,
            ),
            accent_btn(
                "Guardar", icon=I.SAVE,
                on_click=self._on_save, colors=c,
            ),
        ]

        header = ft.Row(
            [
                ft.Text("Configuración", size=22, weight=ft.FontWeight.BOLD, color=c["text"]),
                ft.Container(expand=True),
                self._lock_btn,
                *(action_buttons if not self._locked else []),
            ],
            spacing=10,
        )

        if self._locked:
            main_content = self._build_locked_state()
        else:
            tabs = tabs_control(
                [
                    ("Proveedor IA",  ft.Container(content=self._tab_ia(cfg, c),          expand=True, padding=pad(top=12))),
                    ("Procesado",     ft.Container(content=self._tab_procesado(cfg, c),   expand=True, padding=pad(top=12))),
                    ("Nomenclatura",  ft.Container(content=self._tab_nomenclatura(cfg, c),expand=True, padding=pad(top=12))),
                    ("Ciclos",        ft.Container(content=self._tab_ciclos(cfg, c),       expand=True, padding=pad(top=12))),
                    ("General",       ft.Container(content=self._tab_general(cfg, c),     expand=True, padding=pad(top=12))),
                    ("Prompts LLM",   ft.Container(content=self._tab_prompts(cfg, c),     expand=True, padding=pad(top=12))),
                ],
                selected_index=0, animation_duration=200, expand=True,
                label_color=c["text"], unselected_label_color=c["text_dim"],
                indicator_color=c["accent"],
            )
            main_content = tabs

        return ft.Container(
            expand=True, bgcolor=c["bg"], padding=pad(all=20),
            content=ft.Column([
                header,
                ft.Container(height=12),
                main_content,
            ], expand=True),
        )

    # ── Locked state ──────────────────────────────────────────────

    def _build_locked_state(self) -> ft.Control:
        c = self.colors
        return ft.Container(
            expand=True,
            content=ft.Column(
                [
                    ft.Container(expand=True),
                    ft.Icon(I.LOCK, size=64, color=c["error"]),
                    ft.Container(height=16),
                    ft.Text(
                        "Configuración protegida",
                        size=20, weight=ft.FontWeight.W_600, color=c["text"],
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=8),
                    ft.Text(
                        "Introduce la contraseña para editar la configuración.",
                        size=13, color=c["text_dim"], text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=24),
                    accent_btn(
                        "Desbloquear", icon=I.LOCK_OPEN,
                        on_click=self._on_lock_click, colors=c,
                    ),
                    ft.Container(expand=True),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                expand=True,
            ),
        )

    # ── Lock / Password dialogs ───────────────────────────────────

    def _on_lock_click(self, _e=None):
        cfg = self.app.cfg
        has_password = bool(cfg.get("config_password_hash"))
        if not has_password:
            self._show_set_password_dialog()
        elif self._locked:
            self._show_unlock_dialog()
        else:
            # Re-lock: rebuild in locked state
            self.app._config_view = ConfiguracionView(self.app, unlocked=False)
            self.app.content_container.content = self.app._config_view.root
            self.page.update()

    def _show_set_password_dialog(self):
        c = self.colors
        pw1 = ft.TextField(
            label="Nueva contraseña", password=True, can_reveal_password=True,
            bgcolor=c["input_bg"], border_color=c["border"],
            focused_border_color=c["accent"], color=c["text"],
            cursor_color=c["accent"], border_radius=8, content_padding=pad(h=12, v=10),
        )
        pw2 = ft.TextField(
            label="Confirmar contraseña", password=True, can_reveal_password=True,
            bgcolor=c["input_bg"], border_color=c["border"],
            focused_border_color=c["accent"], color=c["text"],
            cursor_color=c["accent"], border_radius=8, content_padding=pad(h=12, v=10),
        )
        error_text = ft.Text("", color=c["error"], size=11)

        def _confirm(e):
            p1 = pw1.value or ""
            p2 = pw2.value or ""
            if not p1:
                error_text.value = "La contraseña no puede estar vacía"
                self.page.update()
                return
            if p1 != p2:
                error_text.value = "Las contraseñas no coinciden"
                self.page.update()
                return
            self.app.cfg["config_password_hash"] = _md5(p1)
            save_config(self.app.cfg)
            self.page.pop_dialog()
            # Rebuild unlocked (user just set it, stays authenticated)
            self.app._config_view = ConfiguracionView(self.app, unlocked=True)
            self.app.content_container.content = self.app._config_view.root
            self.page.update()
            snack_open(self.page, "Contraseña configurada correctamente", c.get("success", "#4CAF50"), 2500)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Configurar contraseña", color=c["text"]),
            content=ft.Column([
                ft.Text(
                    "Establece una contraseña para proteger la configuración.",
                    size=12, color=c["text_dim"],
                ),
                ft.Container(height=12),
                pw1,
                ft.Container(height=8),
                pw2,
                ft.Container(height=4),
                error_text,
            ], tight=True, width=340),
            bgcolor=c["surface"],
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page.pop_dialog()),
                accent_btn("Guardar", on_click=_confirm, colors=c),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def _show_unlock_dialog(self):
        c = self.colors
        pw = ft.TextField(
            label="Contraseña", password=True, can_reveal_password=True,
            bgcolor=c["input_bg"], border_color=c["border"],
            focused_border_color=c["accent"], color=c["text"],
            cursor_color=c["accent"], border_radius=8, content_padding=pad(h=12, v=10),
            autofocus=True,
        )
        error_text = ft.Text("", color=c["error"], size=11)

        def _confirm(e):
            entered = pw.value or ""
            stored  = self.app.cfg.get("config_password_hash", "")
            if _md5(entered) == stored:
                self.page.pop_dialog()
                self.app._config_view = ConfiguracionView(self.app, unlocked=True)
                self.app.content_container.content = self.app._config_view.root
                self.page.update()
            else:
                error_text.value = "Contraseña incorrecta"
                pw.value = ""
                self.page.update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Desbloquear configuración", color=c["text"]),
            content=ft.Column([
                pw,
                ft.Container(height=4),
                error_text,
            ], tight=True, width=300),
            bgcolor=c["surface"],
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: self.page.pop_dialog()),
                accent_btn("Desbloquear", on_click=_confirm, colors=c),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    # ── Tab: Proveedor IA ─────────────────────────────────────────

    def _tab_ia(self, cfg: dict, c: dict) -> ft.Control:
        self._modo_radio = ft.RadioGroup(
            value="ollama" if cfg.get("modo_desarrollo_prod") else "openrouter",
            on_change=self._on_modo_change,
            content=ft.Row([
                ft.Radio(value="ollama",     label="Ollama (red interna)",     label_style=ft.TextStyle(color=c["text"])),
                ft.Radio(value="openrouter", label="OpenRouter (API externa)", label_style=ft.TextStyle(color=c["text"])),
            ]),
        )

        self._ollama_url     = _textfield(cfg.get("ollama_url"), c)
        self._ollama_model   = _textfield(cfg.get("ollama_model"), c)
        self._ollama_timeout = _textfield(cfg.get("ollama_timeout"), c, width=120)
        self._ollama_retries = _textfield(cfg.get("ollama_max_retries"), c, width=80)
        self._ollama_url.on_change     = self._mark_dirty
        self._ollama_model.on_change   = self._mark_dirty
        self._ollama_timeout.on_change = self._mark_dirty
        self._ollama_retries.on_change = self._mark_dirty

        self._ollama_section = ft.Container(
            visible=cfg.get("modo_desarrollo_prod", False),
            content=ft.Column([
                _field_group("URL del servidor Ollama",
                    "Endpoint de la API. Red interna: http://ollama.iabd.cip.fpmislata.com:80/api/generate",
                    self._ollama_url, c),
                _field_group("Modelo Ollama",
                    "Nombre exacto del modelo instalado en el servidor (ej: llama3.2-vision:11b).",
                    self._ollama_model, c),
                ft.Row([
                    _field_group("Timeout (segundos)",
                        "Tiempo máximo de espera por llamada antes de reintentar.",
                        self._ollama_timeout, c),
                    _field_group("Reintentos",
                        "Nº de reintentos con backoff exponencial (1s, 2s, 4s…).",
                        self._ollama_retries, c),
                ], spacing=20),
            ], spacing=12),
        )

        self._or_url   = _textfield(cfg.get("openrouter_url"), c)
        self._or_model = _textfield(cfg.get("openrouter_model"), c)
        self._or_key   = _textfield(cfg.get("openrouter_api_key"), c, password=True)
        self._or_url.on_change   = self._mark_dirty
        self._or_model.on_change = self._mark_dirty
        self._or_key.on_change   = self._mark_dirty

        self._or_section = ft.Container(
            visible=not cfg.get("modo_desarrollo_prod", False),
            content=ft.Column([
                _field_group("URL API OpenRouter",
                    "Endpoint de la API. No cambiar salvo indicación del proveedor.",
                    self._or_url, c),
                _field_group("Modelo OpenRouter",
                    "ID del modelo (ej: qwen/qwen3-vl-8b-instruct, meta-llama/llama-3.2-11b-vision-instruct).",
                    self._or_model, c),
                _field_group("API Key",
                    "Clave de acceso. Se guarda en config.json local junto a la aplicación.",
                    self._or_key, c),
            ], spacing=12),
        )

        return ft.Column([
            _card(ft.Column([
                ft.Text("Proveedor de IA", size=14, weight=ft.FontWeight.W_700, color=c["text"]),
                ft.Text("Elige el backend de visión que procesará los formularios.", size=11, color=c["text_dim"]),
                ft.Container(height=8),
                self._modo_radio,
            ], spacing=4), c),
            _card(self._ollama_section, c),
            _card(self._or_section, c),
        ], scroll=ft.ScrollMode.AUTO, expand=True)

    def _on_modo_change(self, e):
        is_ollama = e.control.value == "ollama"
        self._ollama_section.visible = is_ollama
        self._or_section.visible = not is_ollama
        self._mark_dirty()
        self.page.update()

    # ── Tab: Procesado ────────────────────────────────────────────

    def _tab_procesado(self, cfg: dict, c: dict) -> ft.Control:
        self._pdf_dpi   = _textfield(cfg.get("pdf_dpi"), c, width=100)
        self._max_pages = _textfield(cfg.get("max_pages_to_analyze"), c, width=80)
        self._yolo_conf = _textfield(cfg.get("yolo_confidence"), c, width=100)
        self._face_pad  = _textfield(cfg.get("face_padding_ratio"), c, width=100)
        self._pdf_limit = _textfield("" if cfg.get("pdf_limit") is None else cfg.get("pdf_limit"), c, width=100)
        self._processed_prefix = _textfield(cfg.get("processed_prefix", "_!_"), c, width=140)
        for f in (self._pdf_dpi, self._max_pages, self._yolo_conf, self._face_pad,
                  self._pdf_limit, self._processed_prefix):
            f.on_change = self._mark_dirty

        self._pasar_grises = _checkbox("Preprocesar página 1 a escala de grises", cfg.get("pasar_a_grises", True), c)
        self._overwrite    = _checkbox("Sobreescribir carpetas existentes",        cfg.get("overwrite_existing", True), c)
        self._debug_repr   = _checkbox("Debug: reprocesar PDFs ya marcados con el prefijo", cfg.get("debug_reprocess", False), c)
        self._pasar_grises.on_change = self._mark_dirty
        self._overwrite.on_change    = self._mark_dirty
        self._debug_repr.on_change   = self._mark_dirty

        return ft.Column([
            _card(ft.Column([
                ft.Text("Conversión de PDF", size=14, weight=ft.FontWeight.W_700, color=c["text"]),
                _field_group("DPI de conversión",
                    "Resolución al convertir cada página a imagen. Mayor DPI = más detalle pero más lento (recomendado: 200).",
                    self._pdf_dpi, c),
                _field_group("Máximo de páginas a analizar",
                    "Nº máximo de páginas analizadas más allá del formulario. Reducir para acelerar.",
                    self._max_pages, c),
                _field_group("Límite de PDFs por ejecución",
                    "Procesar solo los primeros N PDFs. Vacío = sin límite.",
                    self._pdf_limit, c),
            ], spacing=12), c),

            _card(ft.Column([
                ft.Text("Detección de caras (YOLO)", size=14, weight=ft.FontWeight.W_700, color=c["text"]),
                _field_group("Confianza mínima YOLO",
                    "Umbral 0.1–1.0. Valores bajos detectan más caras pero con más falsos positivos.",
                    self._yolo_conf, c),
                _field_group("Padding del recorte de cara",
                    "Expansión alrededor de la cara en fracción de la caja (0.35 = 35% extra).",
                    self._face_pad, c),
            ], spacing=12), c),

            _card(ft.Column([
                ft.Text("Marcado de PDFs procesados", size=14, weight=ft.FontWeight.W_700, color=c["text"]),
                _field_group("Prefijo de PDFs procesados",
                    "Texto que se añade al inicio del nombre del PDF tras procesarlo. "
                    "Al cambiar este valor, los PDFs existentes con el prefijo antiguo se renombrarán automáticamente.",
                    self._processed_prefix, c),
            ], spacing=12), c),

            _card(ft.Column([
                ft.Text("Opciones de procesado", size=14, weight=ft.FontWeight.W_700, color=c["text"]),
                self._pasar_grises,
                ft.Text("  Convierte la pág.1 a grises + umbral Otsu antes del OCR.", size=11, color=c["text_dim"]),
                ft.Container(height=6),
                self._overwrite,
                ft.Text("  Sobreescribe la carpeta de salida si ya existe.", size=11, color=c["text_dim"]),
                ft.Container(height=6),
                self._debug_repr,
                ft.Text("  Reprocesa PDFs con el prefijo de procesado (depuración).", size=11, color=c["text_dim"]),
            ], spacing=4), c),
        ], scroll=ft.ScrollMode.AUTO, expand=True)

    # ── Tab: Nomenclatura ─────────────────────────────────────────

    def _tab_nomenclatura(self, cfg: dict, c: dict) -> ft.Control:
        ac = cfg.get("asistencia_code", {})
        self._code_presencial     = _textfield(ac.get("presencial", "P"),    c, width=80)
        self._code_semipresencial = _textfield(ac.get("semipresencial", "S"),c, width=80)
        self._code_libre          = _textfield(ac.get("libre", "L"),         c, width=80)
        self._code_parcial        = _textfield(ac.get("parcial", "PA"),      c, width=80)
        for f in (self._code_presencial, self._code_semipresencial, self._code_libre, self._code_parcial):
            f.on_change = self._mark_dirty

        _default_fmt = DEFAULTS.get("document_name_format", "")
        self._name_format = ft.TextField(
            value=cfg.get("document_name_format", _default_fmt),
            bgcolor=c["input_bg"], border_color=c["border"],
            focused_border_color=c["accent"], color=c["text"],
            cursor_color=c["accent"], border_radius=8,
            content_padding=pad(h=12, v=10), expand=True,
            text_style=ft.TextStyle(font_family="monospace", size=12),
            on_change=self._on_format_change,
        )
        self._format_status   = ft.Text("", size=11)
        self._format_preview1 = ft.Text("", size=12, selectable=True,
                                        font_family="monospace", color=c["text_muted"])
        self._format_preview2 = ft.Text("", size=12, selectable=True,
                                        font_family="monospace", color=c["text_muted"])
        self._update_format_display(do_update=False)

        def _chip(name: str, desc: str) -> ft.Container:
            return ft.Container(
                content=ft.Text(f"{{{name}}}", size=11, color=c["accent"], font_family="monospace"),
                bgcolor=c["bg"], border=border_all(1, c["border"]),
                border_radius=6, padding=pad(h=8, v=4),
                tooltip=desc,
            )

        return ft.Column([
            _card(ft.Column([
                ft.Text("Códigos de tipo de asistencia", size=14, weight=ft.FontWeight.W_700, color=c["text"]),
                ft.Text(
                    "Código de 1–2 letras que se inserta antes del año en el nombre de carpeta.\n"
                    "Ejemplo: E15001_P2526_M  (P = presencial)",
                    size=11, color=c["text_dim"],
                ),
                ft.Container(height=8),
                ft.Row([
                    _field_group("Presencial",     "Código para modalidad presencial.",  self._code_presencial, c),
                    _field_group("Semipresencial", "Código para semipresencial.",        self._code_semipresencial, c),
                    _field_group("Libre",          "Código para modalidad libre.",       self._code_libre, c),
                    _field_group("Parcial",        "Código para matriculación parcial.", self._code_parcial, c),
                ], spacing=20, wrap=True),
            ], spacing=12), c),

            _card(ft.Column([
                ft.Text("Formato del nombre canónico", size=14, weight=ft.FontWeight.W_700, color=c["text"]),
                ft.Text(
                    "Define la estructura de la carpeta y nombre de fichero. "
                    "Usa los campos entre llaves {}. "
                    "Los campos vacíos (p. ej. apellido2 ausente) se eliminan junto a su separador automáticamente.\n"
                    "Puedes incluir texto fijo directamente (ej: _M al final).",
                    size=11, color=c["text_dim"],
                ),
                ft.Container(height=8),
                ft.Text("Campos disponibles (pasa el ratón para ver descripción):",
                        size=11, weight=ft.FontWeight.W_600, color=c["text_dim"]),
                ft.Container(height=4),
                ft.Row([
                    _chip("nombre",
                          "Nombre de pila del estudiante en mayúsculas ASCII sin acentos.\n"
                          "Ej: JESUS, MARIA, FATIMA"),
                    _chip("apellido1",
                          "Primer apellido en mayúsculas ASCII sin acentos.\n"
                          "Ej: VALVERDE, GARCIA, EL"),
                    _chip("apellido2",
                          "Segundo apellido. Si está vacío se elimina junto al separador anterior.\n"
                          "Ej: LLOBREGAT, LOPEZ — o vacío si el estudiante no tiene segundo apellido"),
                    _chip("expediente",
                          "Número de expediente de 5 dígitos escrito a mano en el formulario.\n"
                          "Ej: 15001, 16237"),
                    _chip("documento",
                          "Número de documento de identidad verificado (DNI, NIE o pasaporte).\n"
                          "Ej: 12345678A (DNI), X1234567B (NIE)"),
                    _chip("asistencia",
                          "Código de tipo de asistencia según la tabla configurada arriba.\n"
                          "Ej: P (presencial), S (semipresencial), L (libre), PA (parcial)"),
                    _chip("año_ini",
                          "Últimos 2 dígitos del año de inicio del curso.\n"
                          "Ej: 25 (para el año 2025)"),
                    _chip("año_fin",
                          "Últimos 2 dígitos del año de fin del curso.\n"
                          "Ej: 26 (para el año 2026)"),
                ], wrap=True, spacing=6),
                ft.Container(height=4),
                ft.Text("Separadores permitidos entre campos:  _ (guión bajo)  ·  , (coma)",
                        size=11, color=c["text_dim"]),
                ft.Container(height=10),
                ft.Row([self._name_format], expand=True),
                ft.Container(height=8),
                self._format_status,
                ft.Container(height=6),
                ft.Text("Vista previa — con segundo apellido:", size=11, color=c["text_dim"]),
                self._format_preview1,
                ft.Container(height=2),
                ft.Text("Vista previa — sin segundo apellido:", size=11, color=c["text_dim"]),
                self._format_preview2,
            ], spacing=4, expand=True), c),

            self._build_structure_card(cfg, c),

        ], scroll=ft.ScrollMode.AUTO, expand=True)

    def _on_format_change(self, _e=None):
        self._mark_dirty()
        self._update_format_display(do_update=True)

    def _update_format_display(self, do_update: bool = True):
        fmt = self._name_format.value.strip()
        valid, msg = _validate_format(fmt)
        self._format_status.value = ("✓  " if valid else "✗  ") + msg
        self._format_status.color = self.colors["success"] if valid else self.colors["error"]
        if valid:
            p1, p2 = _preview_names(fmt)
            self._format_preview1.value = p1
            self._format_preview2.value = p2
        else:
            self._format_preview1.value = ""
            self._format_preview2.value = ""
        if do_update:
            self.page.update()

    # ── Estructura de carpetas output ─────────────────────────────────────────

    def _build_structure_card(self, cfg: dict, c: dict) -> ft.Control:
        default_structure = cfg.get("output_folder_structure", "{ciclo_codigo}")
        valid, msg = validate_structure_template(default_structure)

        self._structure_field = ft.TextField(
            value=default_structure,
            bgcolor=c["input_bg"], border_color=c["border"],
            focused_border_color=c["accent"], color=c["text"],
            cursor_color=c["accent"], border_radius=8,
            content_padding=pad(h=12, v=10), expand=True,
            text_style=ft.TextStyle(font_family="monospace", size=12),
            hint_text="{ciclo_codigo}",
            on_change=self._on_structure_change,
        )
        self._structure_status = ft.Text(
            msg, size=11,
            color=c["success"] if valid else c["error"],
        )
        initial_preview = render_structure_preview(default_structure, _STRUCTURE_PREVIEW_SAMPLES)
        self._structure_preview = ft.Text(
            initial_preview, size=11, selectable=True,
            font_family="monospace", color=c["text_muted"],
        )
        out_dir = cfg.get("output_dir", "")
        _reorg_enabled = bool(out_dir) and valid and bool(default_structure.strip())
        def _reorg_style(enabled: bool) -> ft.ButtonStyle:
            return ft.ButtonStyle(
                color=c["accent"] if enabled else c["text_dim"],
                side=ft.BorderSide(1, c["accent"] if enabled else c["border"]),
            )
        self._reorg_btn = ft.OutlinedButton(
            "Reorganizar output",
            icon=I.DRIVE_FILE_MOVE,
            disabled=not _reorg_enabled,
            on_click=self._on_reorganize_click,
            style=_reorg_style(_reorg_enabled),
        )
        self._reorg_style_fn = _reorg_style
        def _hover_reorg(e, btn=self._reorg_btn, theme_c=c):
            if btn.disabled:
                return
            if e.data == "true":
                btn.style = ft.ButtonStyle(
                    color=theme_c["accent_hover"],
                    side=ft.BorderSide(2, theme_c["accent_hover"]),
                )
            else:
                btn.style = ft.ButtonStyle(
                    color=theme_c["accent"],
                    side=ft.BorderSide(1, theme_c["accent"]),
                )
            btn.update()
        self._reorg_btn_wrapper = ft.GestureDetector(
            mouse_cursor=MC.CLICK if _reorg_enabled else MC.FORBIDDEN,
            content=self._reorg_btn,
            on_hover=_hover_reorg,
        )

        def _chip(name: str, desc: str) -> ft.Container:
            return ft.Container(
                content=ft.Text(f"{{{name}}}", size=11, color=c["accent"],
                                font_family="monospace"),
                bgcolor=c["bg"], border=border_all(1, c["border"]),
                border_radius=6, padding=pad(h=8, v=4), tooltip=desc,
            )

        chips = ft.Row([
            _chip("grado",        "Grado del ciclo: SUPERIOR o MEDIO"),
            _chip("ciclo_codigo", "Código del ciclo: DAW, DAM, ASIR…"),
            _chip("ciclo_nombre", "Nombre completo del ciclo (puede ser largo)"),
            _chip("año_ini",      "Últimos 2 dígitos del año de inicio"),
            _chip("año_fin",      "Últimos 2 dígitos del año de fin"),
            _chip("asistencia",   "Código de modalidad: P, S, L, PA"),
            _chip("expediente",   "Número de expediente"),
        ], wrap=True, spacing=6)

        return _card(ft.Column([
            ft.Text("Estructura de carpetas output", size=14,
                    weight=ft.FontWeight.W_700, color=c["text"]),
            ft.Text(
                "Define subcarpetas entre output/ y la carpeta del expediente. "
                "Vacío = estructura plana (compatible con instalaciones anteriores).\n"
                "'/' separa niveles. 'output/revision/' nunca se ve afectada.",
                size=11, color=c["text_dim"],
            ),
            ft.Container(height=6),
            ft.Text("Campos disponibles:", size=11, weight=ft.FontWeight.W_600,
                    color=c["text_dim"]),
            ft.Container(height=4),
            chips,
            ft.Container(height=8),
            ft.Row([self._structure_field], expand=True),
            ft.Container(height=4),
            self._structure_status,
            ft.Divider(color=c["border"], height=1),
            ft.Text("Vista previa:", size=11, color=c["text_dim"]),
            self._structure_preview,
            ft.Container(height=4),
            ft.Row([ft.Container(expand=True), self._reorg_btn_wrapper]),
        ], spacing=6), c)

    def _on_structure_change(self, e=None):
        self._mark_dirty()
        # Resetear el flag: si cambia template, la reorganización anterior ya no es válida
        self._has_reorganized_this_session = False
        c = self.colors
        tpl = self._structure_field.value or ""
        valid, msg = validate_structure_template(tpl)
        self._structure_status.value = msg
        self._structure_status.color = c["success"] if valid else c["error"]
        if valid:
            self._structure_preview.value = render_structure_preview(
                tpl, _STRUCTURE_PREVIEW_SAMPLES)
        else:
            self._structure_preview.value = "(template no válido)"
        out_dir = self.app.cfg.get("output_dir", "")
        enabled = bool(out_dir) and valid and bool(tpl.strip())
        self._reorg_btn.disabled = not enabled
        self._reorg_btn.style = self._reorg_style_fn(enabled)
        self._reorg_btn_wrapper.mouse_cursor = (
            MC.CLICK if enabled else MC.FORBIDDEN
        )
        self.page.update()

    def _on_reorganize_click(self, e):
        if self._dirty:
            self._show_save_before_reorg_dialog()
        else:
            self._do_reorganize_in_place()

    def _show_save_before_reorg_dialog(self):
        c = self.colors

        def _save_and_reorg(e):
            dlg_close(self.page)
            # Suprimir el diálogo de "estructura cambiada" en _on_save,
            # ya que vamos a reorganizar inmediatamente después.
            self._has_reorganized_this_session = True
            self._on_save(None)
            self._do_reorganize_in_place()

        def _cancel(e):
            dlg_close(self.page)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Cambios sin guardar", color=c["text"]),
            content=ft.Text(
                "Hay cambios sin guardar. Para reorganizar el output con la "
                "estructura actual, primero se guardará la configuración.",
                size=13, color=c["text_dim"],
            ),
            bgcolor=c["surface"],
            actions=[
                ft.OutlinedButton("Cancelar", on_click=_cancel),
                accent_btn(
                    "Guardar y reorganizar", icon=I.DRIVE_FILE_MOVE,
                    on_click=_save_and_reorg, colors=c,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, dlg)

    def _do_reorganize_in_place(self):
        c = self.colors
        out_dir_str = self.app.cfg.get("output_dir", "")
        if not out_dir_str:
            return
        out_dir = Path(out_dir_str)
        # Reorganizar con el template que hay en pantalla (puede no estar guardado aún)
        current_tpl = self._structure_field.value or ""

        def _fmt_t(secs: float) -> str:
            secs = max(0, int(secs))
            h, r = divmod(secs, 3600)
            m, s = divmod(r, 60)
            return f"{h:02d}:{m:02d}:{s:02d}"

        prog_bar     = ft.ProgressBar(value=0, bgcolor=c["surface"], color=c["accent"])
        prog_counter = ft.Text("0 / …", size=15, weight=ft.FontWeight.BOLD, color=c["text"])
        prog_elapsed = ft.Text("00:00:00", size=11, color=c["text_muted"])
        prog_eta     = ft.Text("--:--:--", size=11, color=c["text_muted"])
        prog_text    = ft.Text("Preparando…", size=12, color=c["text_muted"], italic=True)
        stop_ev      = threading.Event()

        time_row = ft.Row([
            ft.Text("Transcurrido", size=10, color=c["text_dim"]), prog_elapsed,
            ft.Container(width=12),
            ft.Text("ETA", size=10, color=c["text_dim"]), prog_eta,
        ], spacing=4)

        def _cancel(e):
            stop_ev.set()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Reorganizando output…", color=c["text"]),
            content=ft.Column([prog_bar, prog_counter, time_row, prog_text],
                              tight=True, spacing=6, width=400),
            bgcolor=c["surface"],
            actions=[ft.OutlinedButton("Cancelar", on_click=_cancel)],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, dlg)

        _reorg_start  = time.time()
        _step_times: list[float] = []
        _last_t       = [_reorg_start]

        def _update_progress(done: int, total: int, name: str):
            now = time.time()
            if done > 0:
                dt = now - _last_t[0]
                if 0 < dt < 300:
                    _step_times.append(dt)
                _last_t[0] = now

            elapsed_s = _fmt_t(now - _reorg_start)
            if _step_times and done < total:
                avg = sum(_step_times[-10:]) / len(_step_times[-10:])
                eta_s = _fmt_t(avg * (total - done))
            elif done >= total > 0:
                eta_s = "00:00:00"
            else:
                eta_s = "--:--:--"

            async def _ui(done=done, total=total, name=name, es=elapsed_s, et=eta_s):
                prog_bar.value     = done / max(total, 1)
                prog_counter.value = f"{done} / {total}"
                prog_elapsed.value = es
                prog_eta.value     = et
                prog_text.value    = name
                prog_bar.update()
                prog_counter.update()
                prog_elapsed.update()
                prog_eta.update()
                prog_text.update()
            self.page.run_task(_ui)

        def _worker():
            status, stats = reorganize_output(
                output_dir=out_dir,
                template=current_tpl,
                on_progress=_update_progress,
                stop_event=stop_ev,
            )
            # Actualizar pending_reorganization en config
            cfg = load_config()
            cfg["pending_reorganization"] = (status != "completed")
            save_config(cfg)
            self.app.cfg = load_config()

            if status == "completed":
                self._has_reorganized_this_session = True

            moved = stats.get("moved", 0)
            failed = stats.get("failed", 0)
            if status == "completed":
                msg = f"Reorganización completada. {moved} expediente(s) movido(s)."
                col = c["success"]
            elif status == "aborted":
                msg = "Reorganización cancelada."
                col = c["warning"]
            else:
                msg = f"Reorganización parcial: {moved} movidos, {failed} error(es)."
                col = c["error"]

            async def _finish(msg=msg, col=col):
                dlg_close(self.page)
                snack_open(self.page, msg, col, 4000)

            self.page.run_task(_finish)

        threading.Thread(target=_worker, daemon=True).start()

    def _show_structure_changed_dialog(self, old_tpl: str, new_tpl: str):
        c = self.colors

        def _change_folder(e):
            dlg_close(self.page)
            snack_open(self.page,
                       "Ve a la pestaña Procesado para cambiar la carpeta de output",
                       c["warning"], 5000)

        def _keep(e):
            dlg_close(self.page)
            snack_open(self.page,
                       "Guardado. Usa 'Reorganizar output' en Nomenclatura para mover "
                       "los expedientes existentes.",
                       c["text_dim"], 5000)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Estructura de carpetas modificada", color=c["text"]),
            content=ft.Column([
                ft.Text(
                    "Los nuevos expedientes se organizarán según la nueva estructura, "
                    "pero los existentes quedan en su ubicación actual.",
                    size=13, color=c["text"],
                ),
                ft.Container(height=6),
                ft.Text(
                    "Para evitar mezclar expedientes con estructuras distintas, "
                    "se recomienda usar el botón 'Reorganizar output' (en la pestaña "
                    "Nomenclatura) o seleccionar una nueva carpeta de output vacía.",
                    size=11, color=c["text_dim"],
                ),
            ], tight=True, spacing=4, width=420),
            bgcolor=c["surface"],
            actions=[
                ft.TextButton("Mantener así", on_click=_keep),
                accent_btn(
                    "Cambiar carpeta output",
                    on_click=_change_folder, colors=c,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dlg_open(self.page, dlg)

    # ── Tab: Ciclos ───────────────────────────────────────────────

    def _tab_ciclos(self, cfg: dict, c: dict) -> ft.Control:
        self._ciclos_column = ft.Column(spacing=4)
        self._ciclo_rows = []

        for codigo, datos in cfg.get("ciclos", {}).items():
            self._add_ciclo_row(codigo, datos["nombre"], datos["grado"])

        return ft.Column([
            _card(ft.Column([
                ft.Text("Catálogo de ciclos formativos", size=14, weight=ft.FontWeight.W_700, color=c["text"]),
                ft.Text(
                    "Define los ciclos reconocidos por el OCR. El código debe coincidir con lo que extrae el modelo "
                    "(o ser normalizable por Levenshtein). El grado determina si aparece en datos.json como 'superior' o 'medio'.",
                    size=11, color=c["text_dim"],
                ),
                ft.Container(height=8),
                ft.Container(
                    content=ft.Row([
                        ft.Text("Código",        size=11, weight=ft.FontWeight.W_700, color=c["text_dim"], width=80),
                        ft.Text("Nombre completo",size=11, weight=ft.FontWeight.W_700, color=c["text_dim"], expand=True),
                        ft.Text("Grado",          size=11, weight=ft.FontWeight.W_700, color=c["text_dim"], width=110),
                        ft.Container(width=44),
                    ]),
                    padding=pad(bottom=4),
                ),
                ft.Divider(height=1, color=c["border"]),
                ft.Container(height=4),
                self._ciclos_column,
                ft.Container(height=8),
                ft.TextButton(
                    "＋ Agregar ciclo", icon=I.ADD,
                    style=ft.ButtonStyle(color=c["accent"]),
                    on_click=lambda _: self._add_ciclo_row("", "", "superior"),
                ),
            ], spacing=4), c),
        ], scroll=ft.ScrollMode.AUTO, expand=True)

    def _add_ciclo_row(self, codigo: str, nombre: str, grado: str):
        c = self.colors
        _kw = dict(
            bgcolor=c["input_bg"], border_color=c["border"], color=c["text"],
            border_radius=6, content_padding=pad(h=8, v=8),
        )
        codigo_f = ft.TextField(value=codigo, width=80,    hint_text="DAW",             **_kw)
        nombre_f = ft.TextField(value=nombre, expand=True, hint_text="Nombre del ciclo", **_kw)
        grado_d  = ft.Dropdown(
            value=grado if grado in ("superior", "medio") else "superior",
            options=[ft.dropdown.Option("superior"), ft.dropdown.Option("medio")],
            bgcolor=c["input_bg"], border_color=c["border"], color=c["text"],
            border_radius=6, content_padding=pad(h=8, v=4), width=110,
        )
        codigo_f.on_change = self._mark_dirty
        nombre_f.on_change = self._mark_dirty
        grado_d.on_select  = self._mark_dirty
        entry = {"codigo": codigo_f, "nombre": nombre_f, "grado": grado_d}

        def _delete(_e, _entry=entry):
            self._ciclos_column.controls.remove(_entry["_row"])
            self._ciclo_rows.remove(_entry)
            self._mark_dirty()
            self.page.update()

        row = ft.Row(
            [codigo_f, nombre_f, grado_d, ft.IconButton(I.DELETE_OUTLINE, icon_color=c["error"], on_click=_delete)],
            spacing=6,
        )
        entry["_row"] = row
        self._ciclo_rows.append(entry)
        self._ciclos_column.controls.append(row)
        self.page.update()

    # ── Tab: Prompts LLM ─────────────────────────────────────────

    def _get_current_ciclos_cfg(self) -> dict:
        """Returns ciclos from live UI rows (or saved config if rows not built yet)."""
        if hasattr(self, '_ciclo_rows') and self._ciclo_rows:
            result = {}
            for entry in self._ciclo_rows:
                k = entry["codigo"].value.strip().upper()
                n = entry["nombre"].value.strip()
                g = entry["grado"].value
                if k and n:
                    result[k] = {"nombre": n, "grado": g}
            if result:
                return result
        return self.app.cfg.get("ciclos", {})

    @staticmethod
    def _render_preview_prompt(template: str, ciclos_cfg: dict) -> str:
        if "{{ciclos}}" not in template:
            return template
        sup = [(k, v["nombre"]) for k, v in ciclos_cfg.items() if v.get("grado") == "superior"]
        med = [(k, v["nombre"]) for k, v in ciclos_cfg.items() if v.get("grado") == "medio"]
        ciclos_text = 'Ciclos posibles — GRADO SUPERIOR (grado = "superior"):\n'
        ciclos_text += "\n".join(f"{k} — {n}" for k, n in sup)
        ciclos_text += '\n\nCiclos posibles — GRADO MEDIO (grado = "medio"):\n'
        ciclos_text += "\n".join(f"{k} — {n}" for k, n in med)
        return template.replace("{{ciclos}}", ciclos_text)

    def _show_prompt_preview(self, prompt_text: str):
        c = self.colors
        rendered = self._render_preview_prompt(prompt_text, self._get_current_ciclos_cfg())
        preview_field = ft.TextField(
            value=rendered,
            read_only=True, multiline=True, min_lines=20, max_lines=40,
            text_style=ft.TextStyle(font_family="monospace", size=11),
            bgcolor=c["input_bg"], border_color=c["border"],
            color=c["text"], cursor_color=c["accent"],
            border_radius=8, content_padding=pad(h=12, v=10),
            expand=True,
        )
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Vista previa del prompt", color=c["text"]),
            content=ft.Column(
                [
                    ft.Text(
                        "Prompt tal como se enviará al modelo — {{ciclos}} sustituido por el listado actual.",
                        size=11, color=c["text_dim"],
                    ),
                    ft.Container(height=8),
                    ft.Row([preview_field], expand=True),
                ],
                spacing=4, expand=True, width=680,
                scroll=ft.ScrollMode.AUTO,
            ),
            bgcolor=c["surface"],
            actions=[
                accent_btn(
                    "Cerrar", on_click=lambda e: self.page.pop_dialog(), colors=c,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def _tab_prompts(self, cfg: dict, c: dict) -> ft.Control:
        def _prompt_area(key: str) -> ft.TextField:
            return ft.TextField(
                value=cfg.get(key, DEFAULTS.get(key, "")),
                multiline=True, min_lines=8, max_lines=20,
                expand=True,
                bgcolor=c["input_bg"], border_color=c["border"],
                focused_border_color=c["accent"], color=c["text"],
                cursor_color=c["accent"], border_radius=8,
                content_padding=pad(h=12, v=10),
                text_style=ft.TextStyle(font_family="monospace", size=12),
            )

        def _restore_btn(field: ft.TextField, key: str) -> ft.TextButton:
            def _restore(_e, _f=field, _k=key):
                _f.value = DEFAULTS.get(_k, "")
                self._mark_dirty()
                self.page.update()
            return ft.TextButton(
                "Restaurar por defecto", icon=I.HISTORY,
                style=ft.ButtonStyle(color=c["text_muted"]),
                on_click=_restore,
            )

        def _preview_btn(field: ft.TextField) -> ft.TextButton:
            def _on_preview(_e, _f=field):
                self._show_prompt_preview(_f.value or "")
            return ft.TextButton(
                "Vista previa", icon=I.VISIBILITY,
                style=ft.ButtonStyle(color=c["accent"]),
                on_click=_on_preview,
            )

        def _prompt_card(
            title: str, description: str, field: ft.TextField, key: str,
            extra_note: ft.Control | None = None, show_preview: bool = False,
        ) -> ft.Container:
            header_controls = [
                ft.Text(title, size=14, weight=ft.FontWeight.W_700, color=c["text"], expand=True),
            ]
            if show_preview:
                header_controls.append(_preview_btn(field))
            header_controls.append(_restore_btn(field, key))
            body: list[ft.Control] = [
                ft.Row(header_controls, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Text(description, size=11, color=c["text_dim"]),
            ]
            if extra_note is not None:
                body.append(extra_note)
            body += [ft.Container(height=6), ft.Row([field], expand=True)]
            return _card(ft.Column(body, spacing=4, expand=True), c)

        ciclos_note = ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Text(
                        "{{ciclos}}", size=11, color=c["accent"], font_family="monospace",
                    ),
                    bgcolor=c["bg"], border=border_all(1, c["border"]),
                    border_radius=6, padding=pad(h=8, v=4),
                ),
                ft.Text(
                    "— se sustituye automáticamente por el listado de ciclos de la pestaña «Ciclos».\n"
                    "No edites la lista directamente aquí; añade o quita ciclos en la pestaña «Ciclos».",
                    size=11, color=c["text_dim"], expand=True,
                ),
            ], spacing=8, wrap=False),
            padding=pad(top=6),
        )

        self._prompt_form            = _prompt_area("prompt_form")
        self._prompt_retry_expediente = _prompt_area("prompt_retry_expediente")
        self._prompt_retry_nombres    = _prompt_area("prompt_retry_nombres")
        self._prompt_retry_apellido2  = _prompt_area("prompt_retry_apellido2")
        self._prompt_page             = _prompt_area("prompt_page")
        for f in (
            self._prompt_form, self._prompt_retry_expediente,
            self._prompt_retry_nombres, self._prompt_retry_apellido2, self._prompt_page,
        ):
            f.on_change = self._mark_dirty

        return ft.Column([
            _card(ft.Column([
                ft.Text("Prompts del modelo de visión", size=14, weight=ft.FontWeight.W_700, color=c["text"]),
                ft.Text(
                    "Edita los textos que se envían al LLM en cada fase del procesado. "
                    "Los cambios se aplican en la próxima ejecución. "
                    "Si borras el texto de un prompt quedará en blanco — usa «Restaurar por defecto» para recuperarlo.",
                    size=11, color=c["text_dim"],
                ),
            ], spacing=4), c),
            _prompt_card(
                "Formulario (página 1)",
                "Prompt principal. Analiza la primera página del PDF (formulario de matrícula) y extrae "
                "expediente, tipo de documento, DNI/NIE, nombre, apellidos, ciclo, tipo de asistencia y curso.",
                self._prompt_form, "prompt_form",
                extra_note=ciclos_note, show_preview=True,
            ),
            _prompt_card(
                "Reintento: Expediente",
                "Se usa automáticamente si el modelo no detectó el número de expediente en la primera pasada. "
                "Focaliza la atención en la esquina superior derecha del formulario.",
                self._prompt_retry_expediente, "prompt_retry_expediente",
            ),
            _prompt_card(
                "Reintento: Nombre y apellidos",
                "Se usa si el modelo no extrajo nombre o primer apellido. "
                "Pide los tres campos (nombre, apellido1, apellido2) por separado.",
                self._prompt_retry_nombres, "prompt_retry_nombres",
            ),
            _prompt_card(
                "Reintento: Segundo apellido",
                "Se usa si el segundo apellido quedó vacío tras el reintento de nombres. "
                "Busca únicamente el campo Apellido 2 del formulario.",
                self._prompt_retry_apellido2, "prompt_retry_apellido2",
            ),
            _prompt_card(
                "Clasificador de páginas (p. 2 en adelante)",
                "Analiza cada página a partir de la segunda para determinar si contiene una foto de carnet, "
                "un documento de identidad (DNI/NIE/pasaporte) u otro contenido. "
                "Si es un documento, también extrae nombre, apellidos y número.",
                self._prompt_page, "prompt_page",
            ),
        ], scroll=ft.ScrollMode.AUTO, expand=True)

    # ── Tab: General ──────────────────────────────────────────────

    def _tab_general(self, cfg: dict, c: dict) -> ft.Control:
        self._log_mode = ft.RadioGroup(
            value=cfg.get("modo_log_fichero", "nuevo"),
            on_change=self._mark_dirty,
            content=ft.Column([
                ft.Radio(value="nuevo",       label="Nuevo fichero en cada ejecución (sobreescribe el anterior)", label_style=ft.TextStyle(color=c["text"])),
                ft.Radio(value="acumular",    label="Acumular — añadir al final del fichero existente",           label_style=ft.TextStyle(color=c["text"])),
                ft.Radio(value="desactivado", label="Desactivado — solo consola, sin fichero",                    label_style=ft.TextStyle(color=c["text"])),
            ], spacing=6),
        )

        self._skip_pending_cb = ft.Checkbox(
            label="No avisar sobre reorganizaciones de output pendientes",
            value=cfg.get("skip_pending_reorganization", False),
            active_color=c["accent"], check_color=c["bg"],
            label_style=ft.TextStyle(color=c["text"], size=13),
            on_change=self._mark_dirty,
        )

        return ft.Column([
            _card(ft.Column([
                ft.Text("Modo de log a fichero", size=14, weight=ft.FontWeight.W_700, color=c["text"]),
                ft.Text(
                    "Controla si la aplicación escribe un fichero de log y cómo lo gestiona entre ejecuciones. "
                    "Los logs se guardan en logs/ junto a la aplicación con nombre procesado_YYYY-MM-DD_HH-MM-SS.log.",
                    size=11, color=c["text_dim"],
                ),
                ft.Container(height=10),
                self._log_mode,
            ], spacing=6), c),
            _card(ft.Column([
                ft.Text("Reorganización de output", size=14, weight=ft.FontWeight.W_700, color=c["text"]),
                ft.Text(
                    "Cuando se cambia la estructura de carpetas output sin reorganizar, "
                    "la app avisa al guardar la configuración. "
                    "Activa esta opción para desactivar ese aviso.",
                    size=11, color=c["text_dim"],
                ),
                ft.Container(height=10),
                self._skip_pending_cb,
            ], spacing=6), c),
        ], scroll=ft.ScrollMode.AUTO, expand=True)

    # ── Save / Reset ──────────────────────────────────────────────

    def _on_save(self, _e):
        cfg = self.app.cfg
        is_ollama = self._modo_radio.value == "ollama"
        cfg["modo_desarrollo_prod"] = is_ollama
        cfg["ollama_url"]         = self._ollama_url.value.strip()
        cfg["ollama_model"]       = self._ollama_model.value.strip()
        cfg["ollama_timeout"]     = _int(self._ollama_timeout.value, 120)
        cfg["ollama_max_retries"] = _int(self._ollama_retries.value, 3)
        cfg["openrouter_url"]     = self._or_url.value.strip()
        cfg["openrouter_model"]   = self._or_model.value.strip()
        cfg["openrouter_api_key"] = self._or_key.value.strip()

        cfg["pdf_dpi"]              = _int(self._pdf_dpi.value, 200)
        cfg["max_pages_to_analyze"] = _int(self._max_pages.value, 6)
        cfg["yolo_confidence"]      = _float(self._yolo_conf.value, 0.35)
        cfg["face_padding_ratio"]   = _float(self._face_pad.value, 0.35)
        lim = self._pdf_limit.value.strip()
        cfg["pdf_limit"]            = _int(lim, None) if lim else None
        cfg["pasar_a_grises"]       = self._pasar_grises.value
        cfg["overwrite_existing"]   = self._overwrite.value
        cfg["debug_reprocess"]      = self._debug_repr.value

        # Handle prefix rename before saving
        new_prefix = self._processed_prefix.value.strip() or "_!_"
        old_prefix = load_config().get("processed_prefix", "_!_")
        if old_prefix != new_prefix:
            history = list(cfg.get("processed_prefix_history", []))
            if old_prefix and old_prefix not in history:
                history.append(old_prefix)
            cfg["processed_prefix_history"] = history[-10:]
            self._rename_prefix_files(old_prefix, new_prefix, cfg.get("input_dir", ""))
        cfg["processed_prefix"] = new_prefix

        cfg["document_name_format"] = self._name_format.value.strip()
        cfg["asistencia_code"] = {
            "presencial":     self._code_presencial.value.strip(),
            "semipresencial": self._code_semipresencial.value.strip(),
            "libre":          self._code_libre.value.strip(),
            "parcial":        self._code_parcial.value.strip(),
        }

        ciclos = {}
        for entry in self._ciclo_rows:
            k = entry["codigo"].value.strip().upper()
            n = entry["nombre"].value.strip()
            g = entry["grado"].value
            if k and n:
                ciclos[k] = {"nombre": n, "grado": g}
        cfg["ciclos"] = ciclos
        cfg["modo_log_fichero"] = self._log_mode.value

        cfg["prompt_form"]             = self._prompt_form.value
        cfg["prompt_retry_expediente"] = self._prompt_retry_expediente.value
        cfg["prompt_retry_nombres"]    = self._prompt_retry_nombres.value
        cfg["prompt_retry_apellido2"]  = self._prompt_retry_apellido2.value
        cfg["prompt_page"]             = self._prompt_page.value

        # Estructura de carpetas output
        prev_structure = (load_config().get("output_folder_structure") or "").strip()
        new_structure  = (self._structure_field.value if self._structure_field else "").strip()
        structure_changed = new_structure != prev_structure
        cfg["output_folder_structure"] = new_structure
        cfg["skip_pending_reorganization"] = (
            self._skip_pending_cb.value if self._skip_pending_cb else False
        )
        if structure_changed and not self._has_reorganized_this_session:
            cfg["pending_reorganization"] = True
        elif structure_changed and self._has_reorganized_this_session:
            cfg["pending_reorganization"] = False

        save_config(cfg)
        self.app.cfg = load_config()
        self._dirty = False

        out_dir = cfg.get("output_dir", "")
        skip    = cfg.get("skip_pending_reorganization", False)
        needs_warning = (
            structure_changed
            and not self._has_reorganized_this_session
            and bool(out_dir)
            and not skip
        )
        if needs_warning:
            self._show_structure_changed_dialog(prev_structure, new_structure)
        else:
            snack_open(self.page, "Configuración guardada correctamente", self.colors["success"], 2000)

    def _rename_prefix_files(self, old_prefix: str, new_prefix: str, input_dir: str):
        if not input_dir or not old_prefix or not new_prefix:
            return
        p = Path(input_dir)
        if not p.exists():
            return
        renamed = 0
        errors = 0
        for pdf in sorted(p.glob("*.pdf")):
            if pdf.name.startswith(old_prefix):
                new_name = new_prefix + pdf.name[len(old_prefix):]
                try:
                    pdf.rename(pdf.parent / new_name)
                    renamed += 1
                except Exception:
                    errors += 1
        if renamed or errors:
            msg = f"Renombrados {renamed} PDF(s) con el nuevo prefijo"
            if errors:
                msg += f" ({errors} error(es))"
            color = self.colors["error"] if errors else self.colors["success"]
            snack_open(self.page, msg, color, 3000)

    def _on_reset(self, _e):
        defaults = get_defaults()
        self.app.cfg.update(defaults)
        self.app._config_view = ConfiguracionView(self.app, unlocked=self._is_authenticated)
        self.app.content_container.content = self.app._config_view.root
        self.page.update()

    def _on_restore_saved(self, _e):
        fresh = load_config()
        self.app.cfg.update(fresh)
        self.app._config_view = ConfiguracionView(self.app, unlocked=self._is_authenticated)
        self.app.content_container.content = self.app._config_view.root
        self.page.update()

    def _on_save_as_default(self, _e):
        save_default_config(self.app.cfg)
        snack_open(
            self.page,
            "Configuración guardada como config_default.json",
            self.colors["success"], 2500,
        )


# ── Value helpers ─────────────────────────────────────────────────────────────

def _int(value, default):
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


def _float(value, default):
    try:
        return float(str(value).strip().replace(",", "."))
    except (ValueError, TypeError):
        return default
