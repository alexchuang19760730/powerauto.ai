@echo off
title PowerAuto Model Downloader
color 0B

echo ============================================
echo   PowerAuto Model Downloader
echo ============================================
echo.
echo Available models:
echo.
echo   1. Qwen3-4B (2GB)         — 轻量级，手机可跑
echo   2. Qwen3-14B (8GB)        — 平衡性能与资源
echo   3. Qwen3.6-35B IQ3 (11GB) — 端侧旗舰
echo   4. Qwen3.6-35B IQ4 (14GB) — 高精度量化
echo   5. Ornith-1.5-35B (14GB)  — Agent 场景首选
echo.
echo Prerequisites:
echo   pip install huggingface_hub
echo.
set /p choice="Select model (1-5): "

mkdir models 2>nul

if "%choice%"=="1" (
    echo Downloading Qwen3-4B...
    huggingface-cli download Qwen/Qwen3-4B-GGUF qwen3-4b-q4_k_m.gguf --local-dir models
) else if "%choice%"=="2" (
    echo Downloading Qwen3-14B...
    huggingface-cli download Qwen/Qwen3-14B-GGUF qwen3-14b-q4_k_m.gguf --local-dir models
) else if "%choice%"=="3" (
    echo Downloading Qwen3.6-35B IQ3...
    huggingface-cli download Alexchuang/cgcengine-models --include "*IQ3_XXS*" --local-dir models
) else if "%choice%"=="4" (
    echo Downloading Qwen3.6-35B IQ4...
    huggingface-cli download Alexchuang/cgcengine-models --include "*denseIQ4X*" --local-dir models
) else if "%choice%"=="5" (
    echo Downloading Ornith-1.5-35B...
    huggingface-cli download Alexchuang/cgcengine-models --include "*Ornith*" --local-dir models
) else (
    echo Invalid choice
    pause
    exit /b 1
)

echo.
echo Download complete! Run start-server.bat to start.
pause
