@echo off
title PowerAuto Local Inference Engine - Installer
color 0A

echo ============================================
echo   PowerAuto Local Inference Engine v1.0
echo   llama-server + CGC Edge Server
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python detected

REM Check if llama-server exists
if exist "llama-server.exe" (
    echo [OK] llama-server.exe found
) else (
    echo [INFO] llama-server.exe not found in current directory
    echo [INFO] Will try to download from GitHub releases...
    echo.
    echo Please download llama-server.exe from one of:
    echo   1. https://github.com/ggerganov/llama.cpp/releases
    echo   2. Build from source: cmake -B build -DGGML_CUDA=ON ^&^& cmake --build build --target llama-server
    echo.
    echo Place llama-server.exe in: %CD%
    echo.
    pause
)

REM Check for model
echo.
echo Checking for models...
set MODEL_FOUND=0
for %%f in (models\*.gguf) do (
    echo   Found: %%f
    set MODEL_FOUND=1
    set MODEL_PATH=%%f
)

if %MODEL_FOUND%==0 (
    echo.
    echo [WARNING] No .gguf model found in models\ directory
    echo.
    echo Please download a model:
    echo   Qwen3.6-35B (11GB):  huggingface-cli download Alexchuang/cgcengine-models
    echo   Qwen3-4B (2GB):      ollama pull qwen3:4b
    echo.
    echo Place .gguf files in: %CD%\models\
    echo.
)

echo.
echo ============================================
echo   Installation Complete!
echo ============================================
echo.
echo To start the server, run:
echo   start-server.bat
echo.
echo The playground will be available at:
echo   https://powerauto.ai/playground/
echo.
echo Configure the playground to connect to:
echo   http://localhost:8080
echo.
pause
