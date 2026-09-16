@echo off
title PowerAuto Local Inference Server
color 0B

echo ============================================
echo   PowerAuto Local Inference Server
echo   OpenAI-Compatible API
echo ============================================
echo.

REM Find model
set MODEL=
for %%f in (models\*.gguf) do (
    if not defined MODEL set MODEL=%%f
)

if not defined MODEL (
    echo [ERROR] No .gguf model found in models\ directory
    echo Please place a .gguf model file in the models\ folder
    pause
    exit /b 1
)

echo Model: %MODEL%
echo.

REM Detect GPU
set NGL=0
where nvidia-smi >nul 2>&1
if %errorlevel%==0 (
    echo [INFO] NVIDIA GPU detected, using CUDA acceleration
    set NGL=99
) else (
    echo [INFO] No NVIDIA GPU, using CPU inference
    set NGL=0
)

REM Settings
set HOST=0.0.0.0
set PORT=8080
set CTX=8192
set THREADS=8

echo Configuration:
echo   Host:     %HOST%:%PORT%
echo   Context:  %CTX%
echo   Threads:  %THREADS%
echo   GPU:      ngl=%NGL%
echo.

echo Starting llama-server...
echo Playground: https://powerauto.ai/playground/
echo API:       http://localhost:%PORT%/v1/chat/completions
echo.

llama-server.exe ^
    -m "%MODEL%" ^
    --host %HOST% ^
    --port %PORT% ^
    -c %CTX% ^
    -ngl %NGL% ^
    -t %THREADS% ^
    --no-webui

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server exited with error code %errorlevel%
    pause
)
