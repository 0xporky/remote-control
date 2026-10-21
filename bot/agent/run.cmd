@echo off
rem One-command launcher for the Agent bot (bot/agent/main.py).
rem
rem Runs from any working directory and when double-clicked from Explorer: the
rem bot resolves .env and the agent entrypoint from __file__, so only this
rem script's own directory matters. On first run it also creates .venv and
rem installs requirements.txt -- the rough equivalent of the Infra bot's
rem `docker compose up -d --build`, except this one stays in the foreground
rem because the agent it spawns needs the interactive desktop session.

setlocal
cd /d "%~dp0"
set "VENV_PY=%CD%\.venv\Scripts\python.exe"

if not exist ".env" (
  echo [run] .env is missing. Copy .env.example to .env and fill in
  echo       TELEGRAM_BOT_TOKEN, ALLOWED_TELEGRAM_USER_ID, PYTHON_BIN.
  goto fail
)

if not exist "%VENV_PY%" (
  echo [run] creating .venv...
  py -3.11 -m venv .venv || py -3 -m venv .venv || python -m venv .venv
  if not exist "%VENV_PY%" (
    echo [run] could not create .venv -- no usable python found on PATH.
    goto fail
  )
  echo [run] installing requirements...
  "%VENV_PY%" -m pip install --quiet --upgrade pip
  "%VENV_PY%" -m pip install --quiet -r requirements.txt || goto fail
)

echo [run] starting agent bot -- keep this window open, Ctrl+C to stop.
"%VENV_PY%" main.py
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo [run] bot exited with code %RC%
  goto fail
)
exit /b 0

:fail
rem Pause when cmd was started just for this script (Explorer double-click, or a
rem PowerShell/bash invocation) so the error does not vanish with the window.
rem Substring test instead of `find`: on a machine with Git's usr/bin on PATH,
rem `find /i "/c"` resolves to GNU find and walks the filesystem.
if not "%CMDCMDLINE:/c=%"=="%CMDCMDLINE%" pause
exit /b 1
