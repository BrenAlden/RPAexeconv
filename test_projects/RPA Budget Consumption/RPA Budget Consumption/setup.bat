@echo off

:: Define the menu path and run the script
set "menu_path=%~dp0codes\View\Menu.py"
python "%menu_path%"

:loop
:: Prompt user for choice
set /p choice=Enter your choice [1-4]: 

:: Strip leading/trailing spaces from input
for /f "tokens=* delims=" %%a in ("%choice%") do set choice=%%a

:: Define the paths
set "main_path=%~dp0codes\Main.py"
set "requirements_path=%~dp0requirements.txt"
set "setup_path=%~dp0codes\Setup.py"

:: Handle user input based on choice
if "%choice%"=="1" (
    echo Starting the program...
    python "%main_path%"
    pause
    cls
    python "%menu_path%"
) else if "%choice%"=="2" (
    echo Installing dependencies...
    python -m pip install -r "%requirements_path%"
    echo Finished installed all dependencies!
    pause
    cls
    python "%menu_path%"
) else if "%choice%"=="3" (
    echo Starting credentials setup window...
    python "%setup_path%"
    cls
    python "%menu_path%"
) else if "%choice%"=="4" (
    echo Exiting program...
    exit
) else (
    echo Invalid choice.
)

goto loop