@echo off
rem Launch the Taipan remake. Extra arguments (--seed N, --fast) are passed through.
set PYTHONPATH=%~dp0src
python -m taipan %*
