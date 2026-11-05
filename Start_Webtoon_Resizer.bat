@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt --quiet
start "" pythonw "%~dp0main.py"
