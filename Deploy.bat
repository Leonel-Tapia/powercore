@echo off
echo =============================================
echo  DEPLOYING CHANGES TO GITHUB AND RAILWAY
echo  powershell / cd C:\powercore

echo =============================================
echo.
git status
echo.
echo Do you want to deploy all changes? (Y/N)
set /p respuesta=
if /i "%respuesta%"=="Y" (
    git add .
    git commit -m "Automatic deployment"
    git push
    echo.
    echo ✅ Changes pushed to GitHub
    echo ⏳ Railway will deploy in 2-3 minutes
) else (
    echo ❌ Cancelled
)
pause