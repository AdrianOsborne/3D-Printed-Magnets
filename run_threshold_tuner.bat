@echo off
echo ==============================
echo Magnet Threshold Tuner
echo ==============================

echo Installing Python requirements...
pip install -r requirements.txt

echo Launching threshold tuner UI...
python threshold_tuner.py

pause
