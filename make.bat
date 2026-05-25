@echo off
setlocal
set PYTHON=.venv\Scripts\python.exe

if "%1"=="" goto :help
if "%1"=="help" goto :help
if "%1"=="test" goto :test
if "%1"=="unit" goto :unit
if "%1"=="integration" goto :integration
if "%1"=="fast" goto :fast
if "%1"=="cov" goto :cov
if "%1"=="clean" goto :clean
if "%1"=="installer" goto :installer
echo Target '%1' desconocido.
goto :help

:test
    %PYTHON% -m pytest tests/ -v
    goto :eof

:unit
    %PYTHON% -m pytest tests/unit/ -v -m unit
    goto :eof

:integration
    %PYTHON% -m pytest tests/integration/ -v -m integration
    goto :eof

:fast
    %PYTHON% -m pytest tests/ -v -m "not slow"
    goto :eof

:cov
    %PYTHON% -m pytest tests/ --cov=modules --cov=utils --cov-report=term-missing --cov-report=html
    goto :eof

:clean
    if exist .coverage del /f .coverage
    if exist htmlcov rd /s /q htmlcov
    if exist .pytest_cache rd /s /q .pytest_cache
    for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
    goto :eof

:installer
    powershell -NoProfile -ExecutionPolicy Bypass -File build\bump_installer.ps1
    goto :eof

:help
    echo.
    echo   make [target]
    echo.
    echo   test          Suite completa
    echo   unit          Solo unit tests (rapidos, sin efectos secundarios)
    echo   integration   Solo integration tests
    echo   fast          Todo excepto @slow
    echo   cov           Suite completa + reporte de cobertura HTML
    echo   clean         Limpia .coverage, htmlcov, __pycache__
    echo   installer     Incrementa version e instala con Inno Setup (Windows)
    echo   help          Muestra esta ayuda
    echo.
