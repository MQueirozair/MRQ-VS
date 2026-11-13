@echo off
rem MRQ VS - sem argumentos abre a janela; com argumentos usa a linha de comando
rem   exemplo: mrq-vs.cmd "https://youtu.be/XXXX"
setlocal
"%~dp0runtime\python.exe" "%~dp0app\run.py" %*
if errorlevel 1 pause
