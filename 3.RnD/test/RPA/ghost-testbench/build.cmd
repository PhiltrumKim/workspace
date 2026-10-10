@echo off
rem GTB-3000 build with the C# compiler bundled in Windows (.NET 3.5, no extra install)
rem Output: dist\GTB3000.exe + dist\GTB3000.exe.config
cd /d "%~dp0"
if not exist dist mkdir dist
"%WINDIR%\Microsoft.NET\Framework\v3.5\csc.exe" -nologo -target:winexe -platform:x86 -optimize+ -codepage:65001 ^
  -out:dist\GTB3000.exe -r:System.dll -r:System.Drawing.dll -r:System.Windows.Forms.dll src\Program.cs
if errorlevel 1 exit /b 1
copy /y src\GTB3000.exe.config dist\ >nul
echo built dist\GTB3000.exe
