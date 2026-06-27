# tidal-downloader-gui
Tidal Download application GUI; this is for personal usage only.

This is a Windows ONLY application.

## Is this code AI generated?
Yeah

## Build code:
`py -m PyInstaller --noconsole --onefile --windowed --icon="app_icon.ico" --collect-all customtkinter main.py`

## Requirements:
`pip install customtkinter tidalapi pillow requests pyinstaller`
`winget install ffmpeg`
`sample_tidal_settings.json` to `tidal_settings.json`. You can keep it like it is, this is for saving your user configs. Note: not sure if this is needed, I just didn't want to leak my own details online.