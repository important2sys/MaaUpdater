@echo off
rem ============================================================
rem  gen-certs.bat  -  regenerate the local CA and leaf cert
rem
rem  Only needed if the certs expire or you want a fresh CA.
rem  Requires openssl (ships with Git for Windows).
rem ============================================================
setlocal
cd /d "%~dp0"

set "CERTDIR=certs"
set "OPENSSL="

if exist "%ProgramFiles%\Git\usr\bin\openssl.exe" set "OPENSSL=%ProgramFiles%\Git\usr\bin\openssl.exe"
if not defined OPENSSL if exist "%ProgramFiles%\Git\mingw64\bin\openssl.exe" set "OPENSSL=%ProgramFiles%\Git\mingw64\bin\openssl.exe"
if not defined OPENSSL if exist "%ProgramFiles(x86)%\Git\usr\bin\openssl.exe" set "OPENSSL=%ProgramFiles(x86)%\Git\usr\bin\openssl.exe"
if not defined OPENSSL where openssl >nul 2>nul
if not defined OPENSSL if not errorlevel 1 set "OPENSSL=openssl"

if not defined OPENSSL echo [ERROR] openssl not found - install Git for Windows or add openssl to PATH
if not defined OPENSSL pause
if not defined OPENSSL exit /b 1

if not exist "%CERTDIR%" mkdir "%CERTDIR%"

> "%CERTDIR%\leaf.ext" echo basicConstraints=critical,CA:FALSE
>>"%CERTDIR%\leaf.ext" echo keyUsage=critical,digitalSignature,keyEncipherment
>>"%CERTDIR%\leaf.ext" echo extendedKeyUsage=serverAuth
>>"%CERTDIR%\leaf.ext" echo subjectAltName=DNS:github.com,DNS:*.github.com,DNS:*.githubusercontent.com,DNS:objects.githubusercontent.com,DNS:release-assets.githubusercontent.com,DNS:codeload.github.com,DNS:api.github.com,DNS:raw.githubusercontent.com
>>"%CERTDIR%\leaf.ext" echo subjectKeyIdentifier=hash
>>"%CERTDIR%\leaf.ext" echo authorityKeyIdentifier=keyid,issuer

echo [1/3] generating CA ...
"%OPENSSL%" req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes -keyout "%CERTDIR%\ghmirror-ca.key" -out "%CERTDIR%\ghmirror-ca.crt" -subj "/CN=RRL Local Mirror CA/O=RRL-LocalOnly" -addext "basicConstraints=critical,CA:TRUE,pathlen:0" -addext "keyUsage=critical,keyCertSign,cRLSign" 2>nul
if errorlevel 1 echo [ERROR] CA generation failed
if errorlevel 1 pause
if errorlevel 1 exit /b 1

echo [2/3] generating leaf cert for github.com ...
"%OPENSSL%" req -newkey rsa:2048 -sha256 -nodes -keyout "%CERTDIR%\github.key" -out "%CERTDIR%\github.csr" -subj "/CN=github.com/O=RRL-LocalOnly" 2>nul
"%OPENSSL%" x509 -req -in "%CERTDIR%\github.csr" -CA "%CERTDIR%\ghmirror-ca.crt" -CAkey "%CERTDIR%\ghmirror-ca.key" -CAcreateserial -out "%CERTDIR%\github.crt" -days 1800 -sha256 -extfile "%CERTDIR%\leaf.ext" 2>nul
if exist "%CERTDIR%\github.csr" del /q "%CERTDIR%\github.csr"

echo [3/3] recording CA thumbprint ...
for /f "usebackq tokens=*" %%T in (`powershell -NoProfile -Command "(New-Object Security.Cryptography.X509Certificates.X509Certificate2 '%CD%\%CERTDIR%\ghmirror-ca.crt').Thumbprint"`) do set "THUMB=%%T"
if defined THUMB >"%CERTDIR%\ca.thumbprint.txt" echo %THUMB%
if defined THUMB echo [OK] thumbprint = %THUMB%
if not defined THUMB echo [WARN] could not read thumbprint, check certs\ca.thumbprint.txt manually

echo.
echo [OK] certs regenerated in %CERTDIR%\
pause
