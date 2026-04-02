@echo off
call "%USERPROFILE%\miniforge3\condabin\conda.bat" activate spinelab-claude
start "" pythonw -m spinelab.main %*
