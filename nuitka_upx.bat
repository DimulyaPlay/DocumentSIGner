set DIST=dist_nuitka\documentSIGner.dist

rem === Основное ===
upx --best --no-lzma --force %DIST%\documentSIGner.exe
upx --best --no-lzma --force %DIST%\python38.dll

rem === DLL ===
upx --best --lzma --force %DIST%\libcrypto-1_1.dll
upx --best --lzma --force %DIST%\libssl-1_1.dll
upx --best --lzma --force %DIST%\libffi-7.dll
upx --best --lzma --force %DIST%\pywintypes38.dll
upx --best --lzma --force %DIST%\pythoncom38.dll
upx --best --lzma --force %DIST%\mupdfcpp64.dll
upx --best --lzma --force %DIST%\pyside2.abi3.dll
upx --best --lzma --force %DIST%\shiboken2.abi3.dll

rem === VC runtime (проверить CFG!) ===
upx --best --lzma --force %DIST%\msvcp140.dll
upx --best --lzma --force %DIST%\msvcp140_1.dll
upx --best --lzma --force %DIST%\vcruntime140.dll
upx --best --lzma --force %DIST%\vcruntime140_1.dll
upx --best --lzma --force %DIST%\concrt140.dll

rem === PYD-файлы ===
for %%f in (%DIST%\*.pyd) do (
    upx --best --lzma --force "%%f"
)

echo Готово!
pause
