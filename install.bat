@echo off
REM Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
REM SPDX-License-Identifier: MIT

REM Trae Agent Installation Script for Windows
REM This script provides an out-of-the-box installation experience for all users

setlocal enabledelayedexpansion

echo.
echo ===============================================
echo    Trae Agent Installation Script for Windows
echo ===============================================
echo.
echo This script will install Trae Agent and its dependencies.
echo Requirements: Python 3.12+, UV package manager
echo.

REM Check if we're in the correct directory
if not exist "pyproject.toml" (
    echo [ERROR] This script must be run from the trae-agent project root directory.
    echo [ERROR] Please navigate to the project directory and run: install.bat
    pause
    exit /b 1
)

if not exist "README.md" (
    echo [ERROR] This script must be run from the trae-agent project root directory.
    echo [ERROR] Please navigate to the project directory and run: install.bat
    pause
    exit /b 1
)

echo [INFO] Checking UV installation...
where uv >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=2" %%i in ('uv --version') do set UV_VERSION=%%i
    echo [SUCCESS] UV is already installed (version: !UV_VERSION!)
) else (
    echo [INFO] UV not found. Installing UV...

    REM Check if PowerShell is available
    where powershell >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] PowerShell is required to install UV automatically.
        echo [ERROR] Please install UV manually from https://docs.astral.sh/uv/
        pause
        exit /b 1
    )

    REM Install UV using PowerShell
    powershell -Command "& {Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression}"

    REM Refresh environment variables
    call refreshenv >nul 2>&1

    REM Check if UV is now available
    where uv >nul 2>&1
    if %errorlevel% equ 0 (
        echo [SUCCESS] UV installed successfully!
    ) else (
        echo [WARNING] UV installation may have succeeded but is not immediately available.
        echo [WARNING] You may need to restart your command prompt or add UV to your PATH.
        echo [WARNING] UV is typically installed to: %USERPROFILE%\.cargo\bin\uv.exe

        REM Try to find UV in common locations
        if exist "%USERPROFILE%\.cargo\bin\uv.exe" (
            set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
            echo [INFO] Found UV in %USERPROFILE%\.cargo\bin, added to PATH for this session.
        ) else (
            echo [ERROR] UV installation failed. Please install UV manually from https://docs.astral.sh/uv/
            pause
            exit /b 1
        )
    )
)

echo.
echo [INFO] Checking Python version...

REM Try python3 first, then python
python3 --version >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=2" %%i in ('python3 --version') do set PYTHON_VERSION=%%i
    set PYTHON_CMD=python3
) else (
    python --version >nul 2>&1
    if %errorlevel% equ 0 (
        for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
        set PYTHON_CMD=python
    ) else (
        echo [ERROR] Python is not installed or not found in PATH.
        echo [ERROR] Please install Python 3.12+ from https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

REM Extract major and minor version numbers
for /f "tokens=1,2 delims=." %%a in ("!PYTHON_VERSION!") do (
    set PYTHON_MAJOR=%%a
    set PYTHON_MINOR=%%b
)

REM Check if Python version is 3.12 or higher
if !PYTHON_MAJOR! lss 3 (
    echo [ERROR] Python !PYTHON_VERSION! is not compatible. Trae Agent requires Python 3.12+
    echo [ERROR] Please install Python 3.12+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

if !PYTHON_MAJOR! equ 3 (
    if !PYTHON_MINOR! lss 12 (
        echo [ERROR] Python !PYTHON_VERSION! is not compatible. Trae Agent requires Python 3.12+
        echo [ERROR] Please install Python 3.12+ from https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

echo [SUCCESS] Python !PYTHON_VERSION! is compatible (requires 3.12+)

echo.
echo [INFO] Setting up virtual environment and dependencies...

REM Check if virtual environment already exists
if exist ".venv" (
    echo [WARNING] Virtual environment already exists. Updating dependencies...
) else (
    echo [INFO] Creating virtual environment...
    uv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo [INFO] Installing dependencies (this may take a few minutes)...
uv sync --all-extras

if %errorlevel% equ 0 (
    echo [SUCCESS] Dependencies installed successfully!
) else (
    echo [ERROR] Failed to install dependencies. Please check the error messages above.
    pause
    exit /b 1
)

echo.
echo [INFO] Setting up configuration...

if not exist "trae_config.yaml" (
    if exist "trae_config.yaml.example" (
        copy "trae_config.yaml.example" "trae_config.yaml" >nul
        echo [SUCCESS] Configuration file created from example template.
        echo [WARNING] Please edit trae_config.yaml to add your API keys before using Trae Agent.
    ) else (
        echo [WARNING] Example configuration file not found. You'll need to create trae_config.yaml manually.
    )
) else (
    echo [INFO] Configuration file already exists.
)

echo.
echo [INFO] Verifying installation...

REM Check if the CLI is available in the virtual environment
if exist ".venv\Scripts\trae-cli.exe" (
    echo [SUCCESS] Trae Agent CLI is available!

    REM Test the CLI
    .venv\Scripts\trae-cli.exe --help >nul 2>&1
    if %errorlevel% equ 0 (
        echo [SUCCESS] Installation verification passed!
    ) else (
        echo [WARNING] CLI installed but may have issues. Try running 'trae-cli --help' after activation.
    )
) else (
    echo [WARNING] CLI verification failed. You may need to activate the virtual environment first.
)

echo.
echo ===============================================
echo            Installation Complete!
echo ===============================================
echo.
echo To get started with Trae Agent:
echo.
echo   1. Activate the virtual environment:
echo      .venv\Scripts\activate
echo.
echo   2. Configure your API keys in trae_config.yaml
echo      Edit the file and add your API keys for your chosen provider(s):
echo      - OpenAI, Anthropic, Google Gemini, OpenRouter, Doubao, etc.
echo.
echo   3. Test the installation:
echo      trae-cli show-config
echo.
echo   4. Run your first task:
echo      trae-cli run "Create a hello world Python script"
echo.
echo   5. For interactive mode:
echo      trae-cli interactive
echo.
echo For more information, see the README.md file or visit:
echo https://github.com/bytedance/trae-agent
echo.
echo Happy coding with Trae Agent! 🤖
echo.

pause
