@echo off
REM ============================================================
REM  Expediente Extractor — Build script (PyInstaller)
REM  Ejecutar desde la raiz del proyecto:
REM    build\build.bat
REM ============================================================

setlocal

set APP_NAME=ExpedienteExtractor
set MAIN_SCRIPT=gui_main.py
set ICON=build\icon.ico
set DIST_DIR=dist
set BUILD_DIR=build\_pyinstaller
set PYTHON=.venv\Scripts\python.exe
set PIP=.venv\Scripts\pip.exe
set PYINSTALLER=.venv\Scripts\pyinstaller.exe

echo.
echo [0/4] Verificando entorno...
if not exist "%PYTHON%" (
    echo [ERROR] No se encontro el entorno virtual en .venv\
    echo         Crea el entorno con: python -m venv .venv
    echo         e instala dependencias: .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

%PIP% show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Instalando PyInstaller...
    %PIP% install pyinstaller
    if errorlevel 1 (
        echo [ERROR] No se pudo instalar PyInstaller.
        pause
        exit /b 1
    )
)

echo.
echo [1/4] Limpiando compilaciones anteriores...
if exist "%DIST_DIR%\%APP_NAME%" rmdir /s /q "%DIST_DIR%\%APP_NAME%"
if exist "%BUILD_DIR%"           rmdir /s /q "%BUILD_DIR%"

echo.
echo [2/4] Compilando con PyInstaller...

REM Construir flag --icon de forma condicional
set ICON_FLAG=
if exist "%ICON%" set ICON_FLAG=--icon "%ICON%"

%PYINSTALLER% ^
    --name "%APP_NAME%" ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --distpath "%DIST_DIR%" ^
    --workpath "%BUILD_DIR%" ^
    --add-data "models;models" ^
    --add-data "modules;modules" ^
    --add-data "utils;utils" ^
    --add-data "gui;gui" ^
    --collect-all flet ^
    --collect-all flet_desktop ^
    --collect-all ultralytics ^
    --hidden-import main ^
    --hidden-import config ^
    --hidden-import cv2 ^
    --hidden-import pymupdf ^
    --hidden-import Levenshtein ^
    --hidden-import requests ^
    --hidden-import gui.app ^
    --hidden-import gui.theme ^
    --hidden-import gui.config_manager ^
    --hidden-import gui.flet_compat ^
    --hidden-import gui.processing_manager ^
    --hidden-import gui.processing_worker ^
    --hidden-import gui.review_manager ^
    --hidden-import gui.system_utils ^
    --hidden-import gui.views.inicio_simple ^
    --hidden-import gui.views.inicio ^
    --hidden-import gui.views.configuracion ^
    --hidden-import gui.views.logs ^
    --hidden-import gui.views.output ^
    --hidden-import gui.views.review_dialog ^
    %ICON_FLAG% ^
    "%MAIN_SCRIPT%"

if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller fallo. Revisa los mensajes anteriores.
    if not defined NOPAUSE pause
    exit /b 1
)

echo.
echo [3/4] Compilacion completada:
echo   %DIST_DIR%\%APP_NAME%\%APP_NAME%.exe
echo.

REM Copiar el icono si existe (para Inno Setup)
if exist "%ICON%" copy /y "%ICON%" "%DIST_DIR%\%APP_NAME%\" >nul

echo [4/4] Generando instalador con Inno Setup...

REM Buscar iscc en ubicaciones habituales
set ISCC=
where iscc >nul 2>&1
if not errorlevel 1 set ISCC=iscc

if "%ISCC%"=="" (
    if exist "%ProgramFiles(x86)%\Inno Setup 6\iscc.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\iscc.exe"
)
if "%ISCC%"=="" (
    if exist "%ProgramFiles%\Inno Setup 6\iscc.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\iscc.exe"
)
if "%ISCC%"=="" (
    if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\iscc.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\iscc.exe"
)

if "%ISCC%"=="" (
    echo NOTA: Inno Setup (iscc.exe) no encontrado.
    echo       Descarga e instala desde: https://jrsoftware.org/isdl.php
    echo       Luego ejecuta manualmente: iscc build\installer.iss
) else (
    "%ISCC%" build\installer.iss
    if not errorlevel 1 (
        echo Instalador generado en: %DIST_DIR%\
    ) else (
        echo [ERROR] Inno Setup fallo. Revisa los mensajes anteriores.
    )
)

echo.
echo BUILD COMPLETADO.
if not defined NOPAUSE pause
