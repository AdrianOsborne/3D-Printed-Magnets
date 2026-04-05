@echo off
echo ==============================
echo Round Whiteboard Magnet Generator
echo ==============================

set INPUT=images
set OUTPUT=out
set THRESHOLDS=thresholds.json

if not exist %OUTPUT% mkdir %OUTPUT%

echo Installing Python requirements...
pip install -r requirements.txt

echo.
echo IMPORTANT:
echo This script needs OpenSCAD installed and in PATH.
echo It outputs STL files only.
echo.

if exist %THRESHOLDS% (
    echo Using threshold overrides from %THRESHOLDS%
    python magnet_generator.py --input %INPUT% --output %OUTPUT% --thresholds-file %THRESHOLDS%
) else (
    echo No thresholds.json found. Using default threshold settings.
    python magnet_generator.py --input %INPUT% --output %OUTPUT%
)

echo.
echo Done.
pause
