@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
set LOG_FILE=%~dp0update_log.txt
echo [%date% %time%] Начало выполнения скрипта >> "%LOG_FILE%"

echo Проверка обновлений и запуск...
ping -n 1 srsfemida >nul 2>&1
if %errorlevel% neq 0 (
    echo [%date% %time%] Ошибка: Сетевой ресурс недоступен. >> "%LOG_FILE%"
    echo Ошибка: Сетевой ресурс недоступен.
    goto :end
)

net use X: \\srsfemida\1$\reference_clients\documentSIGner\ /persistent:no 2>>"%LOG_FILE%" || (
    echo [%date% %time%] Ошибка: Не удалось подключить сетевой диск. Код ошибки: %errorlevel% >> "%LOG_FILE%"
    goto :end
)
echo [%date% %time%] Сетевой диск успешно подключен. >> "%LOG_FILE%"

echo Обновление файлов...
xcopy X:\ /D /E /Y 2>>"%LOG_FILE%" || (
    echo [%date% %time%] Ошибка: Не удалось скопировать файлы. Код ошибки: %errorlevel% >> "%LOG_FILE%"
    goto :unmount
)
echo [%date% %time%] Файлы успешно обновлены. >> "%LOG_FILE%"

:unmount
echo Завершение обновления, отключение диска...
net use /delete X: /YES 2>>"%LOG_FILE%" || (
    echo [%date% %time%] Ошибка: Не удалось отключить сетевой диск. Код ошибки: %errorlevel% >> "%LOG_FILE%"
    goto :end
)
echo [%date% %time%] Сетевой диск успешно отключен. >> "%LOG_FILE%"

:end
echo Запуск documentSIGner.exe...
start "" "%~dp0documentSIGner.exe"
echo [%date% %time%] Запуск программы завершен. >> "%LOG_FILE%"
@exit
