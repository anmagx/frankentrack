@echo off
REM Frankentrack Installation Script
REM Creates virtual environment, installs dependencies, and creates desktop shortcut

setlocal enabledelayedexpansion

echo ========================================
echo   Frankentrack Installation
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher from python.org
    pause
    exit /b 1
)

REM Get Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Found Python %PYTHON_VERSION%
echo.

REM Get the directory where this script is located
set "INSTALL_DIR=%~dp0"
set "INSTALL_DIR=%INSTALL_DIR:~0,-1%"

REM Check if venv already exists
if exist "%INSTALL_DIR%\.venv" (
    echo Virtual environment already exists at: %INSTALL_DIR%\.venv
    choice /C YN /M "Do you want to recreate it"
    if errorlevel 2 goto :skip_venv_creation
    echo Removing existing virtual environment...
    rmdir /s /q "%INSTALL_DIR%\.venv"
)

echo Creating virtual environment...
python -m venv "%INSTALL_DIR%\.venv"
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)
echo Virtual environment created successfully!
echo.

:skip_venv_creation

echo Installing dependencies from requirements.txt...
"%INSTALL_DIR%\.venv\Scripts\python.exe" -m pip install --upgrade pip
"%INSTALL_DIR%\.venv\Scripts\python.exe" -m pip install -r "%INSTALL_DIR%\requirements.txt"
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo Installing pseyepy dependencies from requirements.txt...
"%INSTALL_DIR%\.venv\Scripts\python.exe" -m pip install -r "%INSTALL_DIR%\pseyepy\requirements.txt"
if errorlevel 1 (
    echo ERROR: Failed to install pseyepy dependencies
    pause
    exit /b 1
)

echo Dependencies installed successfully!
echo installing pseyepy...

cd "%INSTALL_DIR%\pseyepy"
"%INSTALL_DIR%\.venv\Scripts\python.exe" -m pip install .
if errorlevel 1 (
    echo ERROR: Failed to install pseyepy
    pause
    exit /b 1
)

cd "%INSTALL_DIR%"

echo pseyepy installed successfully!
echo.


REM Create a launch script
echo Creating launch script...
set "LAUNCH_SCRIPT=%INSTALL_DIR%\launch_frankentrack.bat"
(
    echo @echo off
    echo REM Frankentrack Launcher
    echo cd /d "%%~dp0"
    echo "%%~dp0\.venv\Scripts\python.exe" "%%~dp0\frankentrack.py"
    echo if errorlevel 1 pause
) > "%LAUNCH_SCRIPT%"
echo Launch script created: launch_frankentrack.bat
echo.

REM Ask if user wants to create desktop shortcut
choice /C YN /M "Do you want to create a desktop shortcut"
if errorlevel 2 goto :skip_shortcut

REM Create desktop shortcut using PowerShell
echo Creating desktop shortcut...
powershell -ExecutionPolicy Bypass -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\Desktop\Frankentrack.lnk'); $Shortcut.TargetPath = '%LAUNCH_SCRIPT%'; $Shortcut.WorkingDirectory = '%INSTALL_DIR%'; $Shortcut.IconLocation = '%INSTALL_DIR%\img\icon.ico'; $Shortcut.Description = 'Launch Frankentrack Headtracker'; $Shortcut.Save()"
if errorlevel 1 (
    echo WARNING: Failed to create desktop shortcut
) else (
    echo Desktop shortcut created successfully!
)
echo.

:skip_shortcut

echo ========================================
echo   Installation Complete!
echo ========================================
echo.
echo You can now run Frankentrack by:
echo   1. Double-clicking launch_frankentrack.bat
if exist "%USERPROFILE%\Desktop\Frankentrack.lnk" (
    echo   2. Using the desktop shortcut
)
echo   3. Running: .venv\Scripts\python frankentrack.py
echo.
pause
