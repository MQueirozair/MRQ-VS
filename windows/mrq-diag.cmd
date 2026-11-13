@echo off
rem MRQ VS - diagnostico do pacote
setlocal
"%~dp0runtime\python.exe" "%~dp0app\diag.py" %*
