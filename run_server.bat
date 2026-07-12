@echo off
title MCP Relay Image Analyzer Server
echo ===================================================
echo   Starting MCP Relay Image Analyzer Server...
echo   Working Directory: %~dp0
echo ===================================================
cd /d "%~dp0"
set PYTHONPATH=%~dp0src
.venv\Scripts\python.exe -m mcp_relay_image_analyzer.server
pause
