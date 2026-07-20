@echo off
echo Building exe in progress

pyinstaller --onefile --name "ReportDashboard" --console script.py
echo Готово! Файл в папке dist\
pause