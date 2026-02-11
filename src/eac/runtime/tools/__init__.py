"""Tool implementations: excel, web. All I/O goes through these."""

from eac.runtime.tools.excel import excel_open_workbook, excel_read_table, excel_export
from eac.runtime.tools.web import web_use_system, web_login, web_logout, web_goto_page, web_enter, web_click, web_extract

TOOLS = {
    "excel.open_workbook": excel_open_workbook,
    "excel.read_table": excel_read_table,
    "excel.export": excel_export,
    "web.use_system": web_use_system,
    "web.login": web_login,
    "web.logout": web_logout,
    "web.goto_page": web_goto_page,
    "web.enter": web_enter,
    "web.click": web_click,
    "web.extract": web_extract,
    "set_var": lambda **kw: kw.get("value"),
    "call_result": lambda **kw: None,
    "table.add_column": lambda **kw: None,
    "table.filter": lambda **kw: None,
    "control.for_each": lambda **kw: None,  # stub: body steps run by interpreter later
}
