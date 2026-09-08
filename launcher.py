"""PyInstaller 打包入口（CI 构建 AutoAssets.exe 用）。"""
from auto_assets.app import main

if __name__ == "__main__":
    raise SystemExit(main())
