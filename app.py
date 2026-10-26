import os
from nicegui import ui, app

from ui.pages.work_order import render_work_order_page
from ui.pages.inventory_manage import render_inventory_page
from ui.pages.bom_manage import render_bom_page
from ui.pages.records import render_records_page
from ui.pages.parts import render_part_page
from ui.components import show_issue_dialog, show_return_dialog, show_finish_dialog
from core.services import get_issue_list, get_return_list, get_finish_list

# 1. 确保 static 文件夹存在
os.makedirs('static', exist_ok=True)

# 2. 将本地的 css 文件挂载到系统中
try:
    app.add_static_files('/static', 'static')
    ui.add_css('/static/quasar.css')
    ui.add_css('/static/material-icons.css')
except Exception as e:
    print(f"静态文件挂载失败，请确保 static 文件夹中有 quasar.css 和 material-icons.css: {e}")

current_page = 'wo'

def switch_page(page_name):
    global current_page
    current_page = page_name
    content_area.clear()
    
    with content_area:
        if current_page == 'wo': render_work_order_page()
        elif current_page == 'bom': render_bom_page()
        elif current_page == 'part': render_part_page()
        elif current_page == 'issue':
            render_records_page("生产领料记录", "新建领料", "bg-green-600", show_issue_dialog, get_issue_list)
        elif current_page == 'return':
            render_records_page("生产退料记录", "新建退料", "bg-orange-600", show_return_dialog, get_return_list)
        elif current_page == 'finish':
            render_records_page("成品入库记录", "新增入库", "bg-purple-600", show_finish_dialog, get_finish_list)
        elif current_page == 'inv': render_inventory_page()

with ui.header().classes('bg-blue-800 text-white items-center px-4'):
    ui.label('SMT 线边仓管理系统').classes('text-xl font-bold')

with ui.row().classes('w-full no-wrap h-[calc(100vh-60px)]'):
    with ui.column().classes('w-56 bg-gray-50 border-r p-4'):
        ui.button('工单管理', icon='assignment', on_click=lambda: switch_page('wo')).classes('w-full mb-2').props('flat align=left')
        ui.button('BOM 管理', icon='account_tree', on_click=lambda: switch_page('bom')).classes('w-full mb-2').props('flat align=left')
        ui.button('物料信息', icon='category', on_click=lambda: switch_page('part')).classes('w-full mb-2').props('flat align=left')
        ui.separator().classes('my-2')
        ui.button('生产领料', icon='outbox', on_click=lambda: switch_page('issue')).classes('w-full mb-2').props('flat align=left')
        ui.button('生产退料', icon='input', on_click=lambda: switch_page('return')).classes('w-full mb-2').props('flat align=left')
        ui.button('成品入库', icon='archive', on_click=lambda: switch_page('finish')).classes('w-full mb-2').props('flat align=left')
        ui.separator().classes('my-2')
        ui.button('库存管理', icon='inventory', on_click=lambda: switch_page('inv')).classes('w-full mb-2').props('flat align=left')

    with ui.column().classes('flex-grow p-6 bg-white overflow-auto') as content_area:
        pass

switch_page('wo')

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="SMT系统", host='0.0.0.0', port=8080, reload=False)
