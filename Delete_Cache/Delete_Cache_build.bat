nuitka --standalone --onefile --enable-plugin=pyside6 --windows-disable-console --windows-icon-from-ico=delete.ico Main.py

rmdir /s /q TestRunner.build
rmdir /s /q TestRunner.dist
rmdir /s /q TestRunner.onefile-build