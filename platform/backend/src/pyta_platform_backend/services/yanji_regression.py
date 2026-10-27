"""旧言迹接入导入兼容；正式实现位于 integrations.yanji.query_pack。"""

from pyta_platform_backend.integrations.yanji.query_pack import (
    import_query_pack,
    import_web_query,
    query_drafts,
)

__all__ = ["import_query_pack", "import_web_query", "query_drafts"]
