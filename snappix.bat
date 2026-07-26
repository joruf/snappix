@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Fast path: existing healthy venv — start immediately (no uv download).
if exist "%cd%\.venv\Scripts\python.exe" (
    "%cd%\.venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)" >nul 2>&1
    if not errorlevel 1 (
        echo Snappix: starting with existing .venv...
        "%cd%\.venv\Scripts\python.exe" "%cd%\run.py" %*
        exit /b %ERRORLEVEL%
    )
)

REM Prefer a real local Python 3.12+ for bootstrap (avoid Windows Store stub).
set "BOOTSTRAP_PY="
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "BOOTSTRAP_PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined BOOTSTRAP_PY if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "BOOTSTRAP_PY=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined BOOTSTRAP_PY if exist "%ProgramFiles%\Python312\python.exe" set "BOOTSTRAP_PY=%ProgramFiles%\Python312\python.exe"
if not defined BOOTSTRAP_PY (
    where py >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%P in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do set "BOOTSTRAP_PY=%%P"
    )
)

if defined BOOTSTRAP_PY (
    echo Snappix: bootstrapping with "%BOOTSTRAP_PY%"...
    "%BOOTSTRAP_PY%" "%cd%\install_dependencies.py"
    if errorlevel 1 (
        echo Snappix: dependency installation failed.
        exit /b 1
    )
    if exist "%cd%\.venv\Scripts\python.exe" (
        echo Snappix: starting application...
        "%cd%\.venv\Scripts\python.exe" "%cd%\run.py" %*
        exit /b %ERRORLEVEL%
    )
)

REM Last resort: download project-local uv and managed Python 3.12.
set "RUNTIME_DIR=%cd%\.snappix-runtime"
set "UV_DIR=%RUNTIME_DIR%\uv"
set "UV_EXE=%UV_DIR%\uv.exe"
set "UV_VERSION=0.11.32"
set "UV_ZIP=%TEMP%\snappix-uv-%UV_VERSION%.zip"
set "UV_URL1=https://github.com/astral-sh/uv/releases/download/%UV_VERSION%/uv-x86_64-pc-windows-msvc.zip"
set "UV_URL2=https://releases.astral.sh/github/uv/releases/download/%UV_VERSION%/uv-x86_64-pc-windows-msvc.zip"

if not exist "%UV_EXE%" (
    echo Snappix: downloading uv toolchain...
    mkdir "%UV_DIR%" >nul 2>&1
    del "%UV_ZIP%" >nul 2>&1

    where curl >nul 2>&1
    if not errorlevel 1 (
        curl.exe -fsSL "%UV_URL1%" -o "%UV_ZIP%"
        if errorlevel 1 curl.exe -fsSL "%UV_URL2%" -o "%UV_ZIP%"
    ) else (
        powershell -NoProfile -ExecutionPolicy Bypass -Command ^
            "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $urls=@('%UV_URL1%','%UV_URL2%'); foreach($u in $urls){ try { Invoke-WebRequest -Uri $u -OutFile '%UV_ZIP%' -UseBasicParsing; exit 0 } catch {} }; exit 1"
    )
    if not exist "%UV_ZIP%" (
        echo Snappix: failed to download uv.
        echo Snappix: Install Python 3.12 from https://www.python.org/downloads/ then re-run Snappix.bat
        echo Snappix: Or open this folder and run:  py -3.12 install_dependencies.py
        exit /b 1
    )
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "Expand-Archive -Path '%UV_ZIP%' -DestinationPath '%UV_DIR%' -Force"
    if errorlevel 1 (
        echo Snappix: failed to extract uv.
        exit /b 1
    )
    if not exist "%UV_EXE%" (
        for /r "%UV_DIR%" %%F in (uv.exe) do (
            if not exist "%UV_EXE%" copy /Y "%%F" "%UV_EXE%" >nul
        )
    )
    del "%UV_ZIP%" >nul 2>&1
)

if not exist "%UV_EXE%" (
    echo Snappix: uv executable missing after download.
    echo Snappix: Install Python 3.12 from https://www.python.org/downloads/ then re-run Snappix.bat
    exit /b 1
)

set "UV_CACHE_DIR=%RUNTIME_DIR%\cache"
set "UV_PYTHON_INSTALL_DIR=%RUNTIME_DIR%\python"

echo Snappix: ensuring Python 3.12 runtime...
"%UV_EXE%" python install 3.12
if errorlevel 1 (
    echo Snappix: failed to install managed Python 3.12.
    exit /b 1
)

echo Snappix: running dependency installer...
"%UV_EXE%" run --python 3.12 --no-project python install_dependencies.py
if errorlevel 1 (
    echo Snappix: dependency installation failed.
    exit /b 1
)

if not exist "%cd%\.venv\Scripts\python.exe" (
    echo Snappix: .venv was not created.
    exit /b 1
)

echo Snappix: starting application...
"%cd%\.venv\Scripts\python.exe" "%cd%\run.py" %*
exit /b %ERRORLEVEL%
