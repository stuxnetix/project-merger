@echo off
chcp 65001 >nul
echo Installing Project Merger dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Installation failed.
    pause
    exit /b %errorlevel%
)
echo Done! Run python main.py to start.
pause
