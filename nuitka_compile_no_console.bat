.venv\Scripts\python.exe -m nuitka ^
  --standalone ^
  --enable-plugin=pyside2 ^
  --output-dir=dist_nuitka ^
  --lto=no ^
  --mingw64 ^
  --clang ^
  --include-module=stamp_editor ^
  --include-module=main_functions ^
  --include-module=notifications ^
  --windows-icon-from-ico=icons8-legal-document-64.ico ^
  --include-data-files=icons8-legal-document-64.ico=./ ^
  --include-data-files=Update.exe=./ ^
  --include-data-files=Update.cfg=./ ^
  --include-data-files=dcs.png=./ ^
  --include-data-files=dcs-copy-in-law.png=./ ^
  --include-data-files=dcs-copy-no-in-law.png=./ ^
  --windows-console-mode=disable ^
  documentSIGner.py
