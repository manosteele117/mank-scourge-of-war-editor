@echo off
setlocal

REM ---------------------------------------------------------------
REM Mank Scourge of War Editor launcher
REM
REM Behaviour:
REM   1. Verify Python is on PATH.
REM   2. If .venv is missing, automatically run install.py to set
REM      things up, then continue.
REM   3. Verify the venv has all required modules installed.
REM   4. Launch main.py using the venv's Python.
REM ---------------------------------------------------------------

cd /d "%~dp0"

set "VENV_DIR=%CD%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

echo ================================================================
echo   Mank Scourge of War Editor - Launcher
echo ================================================================
echo.

REM --- 1. Locate a working Python interpreter --------------------------
set "PYTHON_CMD="
where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    goto :have_python
)
where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    goto :have_python
)

echo.
echo ERROR: Python is not installed or not on your PATH.
echo.
echo   To fix this:
echo     1. Download Python 3.10 or later from
echo        https://www.python.org/downloads/
echo     2. During installation, check the box that says
echo        "Add Python to PATH".
echo     3. Re-run this file.
echo.
pause
exit /b 1

:have_python
echo [*] Using Python command: %PYTHON_CMD%

REM --- 2. Make sure the venv exists ------------------------------------
if exist "%VENV_PY%" goto :venv_ready

echo.
echo [!] Virtual environment not found at:
echo     %VENV_DIR%
echo.
echo The first-time setup will now run. This may take several minutes
echo depending on your internet speed, because it will:
echo   - create a new virtual environment
echo   - download and install PySide6, pandas, numpy, Pillow, and matplotlib
echo.
echo Please wait until it finishes...
echo.

%PYTHON_CMD% install.py
if errorlevel 1 (
    echo.
    echo ERROR: Installation failed. See the messages above for details.
    echo Re-run run.bat once you have fixed the issue.
    echo.
    pause
    exit /b 1
)

if not exist "%VENV_PY%" (
    echo.
    echo ERROR: Installation reported success, but %VENV_PY%
    echo        is still missing. Check the installer output above.
    echo.
    pause
    exit /b 1
)

:venv_ready
if not exist "%VENV_PY%" (
    echo.
    echo ERROR: %VENV_PY% is not a file.
    echo        The virtual environment looks broken. Delete the .venv
    echo        folder and run this file again so it can be rebuilt.
    echo.
    pause
    exit /b 1
)

REM --- 3. Sanity-check the venv's installed modules --------------------
"%VENV_PY%" -c "import PySide6, pandas, numpy, PIL, matplotlib" >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: The virtual environment is present but one or more
    echo        required modules ^(PySide6, pandas, numpy, Pillow,
    echo        matplotlib^) failed to import.
    echo.
    echo        To repair, delete the .venv folder and re-run this file.
    echo        It will automatically rebuild the environment.
    echo.
    pause
    exit /b 1
)

REM --- 4. Launch the editor --------------------------------------------
echo [*] Starting Mank Scourge of War Editor...
echo.
"%VENV_PY%" main.py
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo ERROR: The editor exited with code %EXITCODE%.
    echo        If this is a Python traceback, see the output above.
    echo.
    pause
)

endlocal & exit /b %EXITCODE%
