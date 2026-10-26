import pandas as pd
from nicegui import ui
from core.services import calculate_loss

def render_loss_page():
    ui.label('工单损耗计算').classes('text-2xl font-bold mb-4')
    
    with ui.row().classes('w-full items-center gap-4 mb-4'):
        wo_input = ui.input('输入工单号查询').classes('w-64')
        ui.button('计算损耗', on_click=lambda: run_search()).classes('bg-blue-600 text-white')
        
    result_container = ui.column().classes('w-full')

    def run_search():
        result_container.clear()
        if not wo_input.value: return
        data = calculate_loss(wo_input.value)
        
        with result_container:
            if not data:
                ui.label('未找到该工单的数据').classes('text-red-500')
                return
            
            ui.table(columns=[
                {'name': '物料料号', 'label': '物料料号', 'field': '物料料号'},
                {'name': '需求数量', 'label': '需求数量', 'field': '需求数量'},
                {'name': '领料数量', 'label': '领料数量', 'field': '领料数量'},
                {'name': '退料数量', 'label': '退料数量', 'field': '退料数量'},
                {'name': '损耗数量', 'label': '损耗数量', 'field': '损耗数量'},
            ], rows=data).classes('w-full shadow-sm border rounded')

            def export_loss():
                pd.DataFrame(data).to_csv('loss_export.csv', index=False, encoding='utf-8-sig')
                ui.download('loss_export.csv')
                ui.notify('导出成功', type='positive')
            ui.button('导出 CSV', icon='download', on_click=export_loss).classes('mt-4 bg-gray-600 text-white').props('dense')
