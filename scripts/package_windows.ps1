$ErrorActionPreference = "Stop"

uv run --extra package pyinstaller `
  --name AirPilot `
  --onedir `
  --clean `
  --noconfirm `
  --paths src `
  --collect-all mediapipe `
  --collect-all cv2 `
  --hidden-import tkinter `
  --hidden-import tkinter.ttk `
  --hidden-import pyautogui `
  src/airpilot/app.py

Write-Host "Packaged AirPilot under dist\AirPilot"
