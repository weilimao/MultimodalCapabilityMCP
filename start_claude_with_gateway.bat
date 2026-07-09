@echo off
title Claude Code with Multimodal Gateway
echo ================================================================
echo   Claude Code Multimodal Gateway Starter
echo ================================================================
echo.
echo [*] Setting ANTHROPIC_BASE_URL to http://127.0.0.1:18449 ...
set ANTHROPIC_BASE_URL=http://127.0.0.1:18449

echo [*] Switching working directory to user home...
cd /d "%USERPROFILE%"

echo [*] Starting Claude Code...
echo.
call claude %*

if %errorlevel% neq 0 (
    echo.
    echo [!] Claude Code exited with error.
    pause
)
