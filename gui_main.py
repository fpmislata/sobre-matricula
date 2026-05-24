import flet as ft
from gui.app import DNIApp


def main(page: ft.Page):
    app = DNIApp(page)
    app.build()


if __name__ == "__main__":
    ft.run(main)
