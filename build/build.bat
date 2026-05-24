@echo off
REM ============================================================
REM  Expediente Extractor — Build script (PyInstaller)
REM  Ejecutar desde la raiz del proyecto con el venv activado:
REM    .venv\Scripts\activate
REM    build\build.bat
REM ============================================================

setlocal

set APP_NAME=ExpedienteExtractor
set MAIN_SCRIPT=gui_main.py
set ICON=build\icon.ico
set DIST_DIR=dist
set BUILD_DIR=build\_pyinstaller

echo.
echo [1/3] Limpiando compilaciones anteriores...
if exist "%DIST_DIR%\%APP_NAME%" rmdir /s /q "%DIST_DIR%\%APP_NAME%"
if exist "%BUILD_DIR%"           rmdir /s /q "%BUILD_DIR%"

echo.
echo [2/3] Compilando con PyInstaller...

pyinstaller ^
    --name "%APP_NAME%" ^
    --noconfirm ^
    --onedir ^
    --windowed ^
    --distpath "%DIST_DIR%" ^
    --workpath "%BUILD_DIR%" ^
    --specpath "%BUILD_DIR%" ^
    --add-data "models;models" ^
    --add-data "modules;modules" ^
    --add-data "utils;utils" ^
    --hidden-import flet ^
    --hidden-import flet.fastapi ^
    --hidden-import ultralytics ^
    --hidden-import cv2 ^
    --hidden-import pymupdf ^
    --hidden-import Levenshtein ^
    "%MAIN_SCRIPT%"

if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller fallo. Revisa los mensajes anteriores.
    pause
    exit /b 1
)

echo.
echo [3/3] Compilacion completada:
echo   %DIST_DIR%\%APP_NAME%\%APP_NAME%.exe
echo.

REM Copiar el icono si existe
if exist "%ICON%" copy /y "%ICON%" "%DIST_DIR%\%APP_NAME%\" >nul

REM Verificar si Inno Setup esta disponible para generar el instalador
where iscc >nul 2>&1
if not errorlevel 1 (
    echo Generando instalador con Inno Setup...
    iscc build\installer.iss
    if not errorlevel 1 echo Instalador generado en dist\ExpedienteExtractorSetup.exe
) else (
    echo NOTA: Inno Setup (iscc) no encontrado. Saltando generacion del instalador.
    echo       Descarga: https://jrsoftware.org/isdl.php
)

echo.
echo BUILD COMPLETADO.
pause
