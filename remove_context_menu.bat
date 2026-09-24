@echo off
setlocal

reg delete "HKCU\Software\Classes\*\shell\DocumentSIGner" /f >nul 2>&1
reg delete "HKLM\Software\Classes\*\shell\DocumentSIGner" /f >nul 2>&1

reg query "HKCU\Software\Classes\*\shell\DocumentSIGner" >nul 2>&1
if not errorlevel 1 (
    echo Не удалось удалить пользовательский пункт контекстного меню.
    exit /b 1
)

reg query "HKLM\Software\Classes\*\shell\DocumentSIGner" >nul 2>&1
if not errorlevel 1 (
    echo Системный пункт не удален. Запустите этот BAT от имени администратора.
    exit /b 2
)

echo Пункт контекстного меню DocumentSIGner удален.
exit /b 0
