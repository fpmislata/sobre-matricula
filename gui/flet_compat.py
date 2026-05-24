"""Helpers that replicate the Flet <0.80 shorthand API for Flet 0.85+."""
import flet as ft

I = ft.Icons       # ft.icons.X → I.X
MC = ft.MouseCursor  # ft.MouseCursor.CLICK / FORBIDDEN / BASIC


def dlg_open(page: ft.Page, dlg: ft.AlertDialog) -> None:
    """Show an AlertDialog using the Flet 0.85 API."""
    page.show_dialog(dlg)


def dlg_close(page: ft.Page, _dlg=None) -> None:
    """Close the current AlertDialog using the Flet 0.85 API."""
    page.pop_dialog()


def snack_open(page: ft.Page, msg: str, bgcolor: str, duration_ms: int = 2500) -> None:
    """Show a SnackBar using page.show_dialog (works for SnackBar in Flet 0.85)."""
    page.show_dialog(ft.SnackBar(
        ft.Text(msg, color="#ffffff"),
        bgcolor=bgcolor,
        duration=ft.Duration(milliseconds=duration_ms),
    ))


def pad(all=None, *, h=None, v=None, left=0, top=0, right=0, bottom=0) -> ft.Padding:
    if all is not None:
        return ft.Padding(left=all, top=all, right=all, bottom=all)
    if h is not None or v is not None:
        return ft.Padding(left=h or 0, top=v or 0, right=h or 0, bottom=v or 0)
    return ft.Padding(left=left, top=top, right=right, bottom=bottom)


def mar(all=None, *, h=None, v=None, left=0, top=0, right=0, bottom=0) -> ft.Margin:
    if all is not None:
        return ft.Margin(left=all, top=all, right=all, bottom=all)
    if h is not None or v is not None:
        return ft.Margin(left=h or 0, top=v or 0, right=h or 0, bottom=v or 0)
    return ft.Margin(left=left, top=top, right=right, bottom=bottom)


def border_all(width: float, color: str) -> ft.Border:
    s = ft.BorderSide(width, color)
    return ft.Border(top=s, right=s, bottom=s, left=s)


def border_only(*, left=None, top=None, right=None, bottom=None) -> ft.Border:
    none_side = ft.BorderSide(0)
    return ft.Border(
        left=left   or none_side,
        top=top     or none_side,
        right=right or none_side,
        bottom=bottom or none_side,
    )


def action_icon_btn(
    *,
    icon,
    icon_color: str,
    tooltip: str,
    on_click,
    disabled: bool = False,
    icon_size: int = 16,
    hover_color: str | None = None,
) -> ft.GestureDetector:
    """IconButton wrapped in GestureDetector with pointer or forbidden cursor.

    Pass hover_color to get a visible background highlight on hover when enabled.
    """
    btn = ft.IconButton(
        icon=icon,
        icon_color=icon_color,
        tooltip=tooltip,
        icon_size=icon_size,
        on_click=on_click,
        disabled=disabled,
    )
    inner = ft.Container(content=btn, border_radius=8)

    if hover_color and not disabled:
        def _hover(e, _c=inner):
            _c.bgcolor = hover_color if e.data == "true" else None
            _c.update()
        on_hov = _hover
    else:
        on_hov = None

    return ft.GestureDetector(
        mouse_cursor=MC.FORBIDDEN if disabled else MC.CLICK,
        content=inner,
        on_hover=on_hov,
    )


def accent_btn(
    text: str,
    *,
    icon=None,
    on_click=None,
    colors: dict,
    disabled: bool = False,
) -> ft.GestureDetector:
    """OutlinedButton transparente con borde accent — mismo estilo que vaciar papelera.

    Normal: borde 1px accent, texto accent, fondo transparente.
    Hover:  borde 2px accent_hover, texto accent_hover.
    Disabled: borde text_dim, texto text_dim.
    Para acceder al OutlinedButton interno: wrapper.content.
    """
    def _style_enabled():
        return ft.ButtonStyle(
            color=colors["accent"],
            side=ft.BorderSide(1, colors["accent"]),
        )

    def _style_hover():
        return ft.ButtonStyle(
            color=colors["accent_hover"],
            side=ft.BorderSide(2, colors["accent_hover"]),
        )

    def _style_disabled():
        return ft.ButtonStyle(
            color=colors["text_dim"],
            side=ft.BorderSide(1, colors["border"]),
        )

    btn = ft.OutlinedButton(
        text, icon=icon,
        style=_style_disabled() if disabled else _style_enabled(),
        on_click=on_click,
        disabled=disabled,
    )

    def _hover(e):
        if btn.disabled:
            return
        btn.style = _style_hover() if e.data == "true" else _style_enabled()
        btn.update()

    return ft.GestureDetector(
        mouse_cursor=MC.FORBIDDEN if disabled else MC.CLICK,
        content=btn,
        on_hover=_hover,
    )


def safe_update(page: ft.Page) -> None:
    """Thread-safe page.update() for background threads.

    Schedules the update on Flet's async event loop via run_task() instead of
    calling page.update() directly, which does not trigger a render from threads.
    """
    async def _upd():
        page.update()
    try:
        page.run_task(_upd)
    except Exception:
        pass


def tabs_control(
    tab_items,
    *,
    selected_index=0,
    animation_duration=200,
    expand=True,
    label_color=None,
    unselected_label_color=None,
    indicator_color=None,
):
    """Build Tabs using Flet 0.85+ API (TabBar + TabBarView)."""
    bar_tabs = [ft.Tab(label=label) for label, _ in tab_items]

    views = [content for _, content in tab_items]
    return ft.Tabs(
        selected_index=selected_index,
        animation_duration=animation_duration,
        expand=expand,
        length=len(bar_tabs),
        content=ft.Column(
            controls=[
                ft.TabBar(
                    tabs=bar_tabs,
                    label_color=label_color,
                    unselected_label_color=unselected_label_color,
                    indicator_color=indicator_color,
                ),
                ft.TabBarView(controls=views, expand=True),
            ],
            expand=True,
        ),
    )

