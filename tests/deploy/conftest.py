"""发布脚本测试不连接SSH或生产数据库。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deploy/scripts"))
