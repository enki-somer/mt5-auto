@echo off
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
python -m pip install "pyinstaller>=6.0,<7"
pyinstaller --noconfirm trade-aut.spec
if exist ".env" copy /Y ".env" "dist\TelegramMT5\.env"
if not exist "dist\TelegramMT5\data" mkdir "dist\TelegramMT5\data"
if exist "data\telegram.session" copy /Y "data\telegram.session" "dist\TelegramMT5\data\telegram.session"
if exist "data\telegram.session-journal" copy /Y "data\telegram.session-journal" "dist\TelegramMT5\data\telegram.session-journal"
echo.
echo Built folder: dist\TelegramMT5
echo Copy that whole folder to the other Windows PC and run TelegramMT5.exe
echo That PC does not need Python. It still needs MetaTrader 5 Desktop if you want MT5.
