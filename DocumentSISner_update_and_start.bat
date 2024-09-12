@Echo off
chcp 65001 >nul
echo Подключение сетевого диска...
net use X: \\srsfemida\1$\DocumentSIGner\ /persistent:no
if %errorlevel% neq 0 (
    echo Ошибка: Не удалось подключить сетевой диск.
) else (
    echo Сетевой диск подключен успешно.
    echo Обновление файлов...
    xcopy X:\ /D /E /Y >nul
    if %errorlevel% neq 0 (
        echo Ошибка: Не удалось скопировать файлы.
    ) else (
        echo Файлы успешно обновлены.
    )
    echo Отключение сетевого диска...
    net use /delete X: /YES
)

echo Запуск documentSIGner.exe...
start documentSIGner.exe
@exit