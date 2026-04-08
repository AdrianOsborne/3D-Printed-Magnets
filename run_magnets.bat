@echo off
echo =====================
echo Magnet Studio
echo =====================

echo Installing Python requirements...
pip install -r requirements.txt

echo.
echo Launching Magnet Studio at http://127.0.0.1:5000
echo Make sure OpenSCAD is installed and available in PATH before generating STL files.
echo.

python app.py
