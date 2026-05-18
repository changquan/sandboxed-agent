@echo off
if exist ".venv\Scripts\chainlit.exe" (
    .venv\Scripts\chainlit.exe run app.py
) else (
    "C:\Users\yucha\AppData\Roaming\Python\Python311\Scripts\chainlit.exe" run app.py
)
