@echo off
title 在线视频实时字幕 - 本地识别服务
cd /d "%~dp0"

rem 需要自定义识别模型/翻译策略时，取消下面某行注释并按需修改（参考 docs\使用指南.md 第五节）
rem set OT_MODEL=medium
rem set OT_TRANSLATOR=nllb

call conda activate ot
if errorlevel 1 (
    echo.
    echo [错误] Conda 环境 ot 激活失败
    echo        请确认已安装 Miniconda/Anaconda 且已创建 ot 环境
    echo.
    pause
    exit /b 1
)

echo ================================================
echo   在线视频实时字幕 - 本地识别服务
echo   服务地址: ws://127.0.0.1:8765/ws
echo   保持本窗口开启，关闭窗口即停止服务
echo ================================================
echo.

python server\main.py

echo.
echo 服务已退出，错误码: %errorlevel%
pause
