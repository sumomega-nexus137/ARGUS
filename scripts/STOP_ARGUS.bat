@echo off
cd /d "%~dp0.."
docker compose stop
echo ARGUS stopped. Data volumes were kept.
pause
