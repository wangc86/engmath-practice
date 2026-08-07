import sys
from pathlib import Path

# 讓 `pytest` 從專案根目錄執行時找得到 app 套件
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
