.venv\Scripts\python.exe -m nuitka ^
  --standalone ^
  --enable-plugin=pyside2 ^
  --output-dir=dist_nuitka ^
  --lto=no ^
  --mingw64 ^
  --clang ^
  --nofollow-import-to=reportlab.graphics.testshapes ^
  --noinclude-unittest-mode=error ^
  --windows-icon-from-ico=icons8-legal-document-64.ico ^
  --include-data-files=icons8-legal-document-64.ico=./ ^
  --include-data-files=Update.exe=./ ^
  --include-data-files=Update.cfg=./ ^
  --include-data-files=dcs.png=./ ^
  --include-data-files=35.gif=./ ^
  --include-data-files=dcs-copy-in-law.png=./ ^
  --include-data-files=dcs-copy-no-in-law.png=./ ^
  --windows-console-mode=disable ^
  documentSIGner.py

nuitka_upx.bat
