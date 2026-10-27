"""为平台和执行引擎的回归测试准备 src 搜索路径。

后端 Python 包位于 platform/backend/src，以避免与标准库 platform 冲突。
测试不依赖已经退役的根目录脚本框架。
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_SRC = REPO_ROOT / "src"
BACKEND_SRC = REPO_ROOT / "platform" / "backend" / "src"


def _ensure_python_path(path: Path) -> None:
    """把目录安全地加入 Python 搜索路径。

    这个辅助函数做的事情很简单，但专门封装出来是为了让新手读代码时更容易理解：
    - 为什么要加路径
    - 加的是哪个路径
    - 如何避免重复插入
    """

    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


_ensure_python_path(ENGINE_SRC)
_ensure_python_path(BACKEND_SRC)
