import pandas as pd
from nicegui import ui
from core.services import get_bom_headers, delete_boms, get_bom_details, get_bom_export_details
from ui.components import show_add_bom_dialog, show_view_bom_dialog
from core.utils import export_to_csv

def render_bom_page():
    state = {'page': 1, 'total': 0, 'size': 20}

    def export_details():
        table = table_container.default_slot.children[0]
        selected_rows = table.selected
        if not selected_rows:
            return ui.notify('请先勾选需要导出的 BOM', type='warning')
        
        bom_ids = [row['id'] for row in selected_rows]
        details = get_bom_export_details(bom_ids)
        
        if not details:
            return ui.notify('选中的 BOM 下没有明细数据', type='warning')
            
        df = pd.DataFrame(details)
        export_to_csv(df, 'bom_details_export.csv')

    def export_data():
        records, _ = get_bom_headers(1, 10000)
        rows = [{'成品料号': r.product_number, '成品名称': r.product_name, '版本号': r.version} for r in records]
        df = pd.DataFrame(rows)
        export_to_csv(df, 'bom_export.csv')

    with ui.row().classes('w-full justify-between items-center mb-4 border-b pb-4'):
        ui.label('BOM 管理').classes('text-2xl font-bold')
        with ui.row():
            ui.button('导出主表', icon='download', on_click=export_data).classes('bg-gray-600 text-white').props('dense')
            ui.button('导出明细', icon='download', on_click=export_details).classes('bg-orange-600 text-white').props('dense')
            ui.button('新增 BOM', icon='add', on_click=lambda: show_add_bom_dialog(load_table)).classes('bg-blue-600 text-white').props('dense')

    table_container = ui.column().classes('w-full')
    
    with ui.row().classes('w-full justify-end items-center mt-4'):
        ui.button(icon='chevron_left', on_click=lambda: change_page(-1)).props('flat')
        page_label = ui.label('第 1 页').classes('mx-2')
        ui.button(icon='chevron_right', on_click=lambda: change_page(1)).props('flat')

    def change_page(delta):
        max_pages = max(1, (state['total'] + state['size'] - 1) // state['size'])
        new_page = state['page'] + delta
        if 1 <= new_page <= max_pages:
            state['page'] = new_page
            load_table()

    def load_table():
        table_container.clear()
        records, total = get_bom_headers(state['page'], state['size'])
        state['total'] = total
        page_label.set_text(f'第 {state["page"]} / {max(1, (total + 19) // 20)} 页 (共 {total} 条)')
        
        rows = [{'id': r.id, '成品料号': r.product_number, '成品名称': r.product_name, '版本号': r.version} for r in records]
        
        with table_container:
            table = ui.table(columns=[
                {'name': '成品料号', 'label': '成品料号', 'field': '成品料号'},
                {'name': '成品名称', 'label': '成品名称', 'field': '成品名称'},
                {'name': '版本号', 'label': '版本号', 'field': '版本号'},
                {'name': '操作', 'label': '操作', 'field': '操作'},
            ], rows=rows, row_key='id', selection='multiple').classes('w-full shadow-sm border rounded').props('flat bordered')
            
            table.add_slot('body-cell-操作', '''
                <q-td :props="props">
                    <q-btn size="sm" color="primary" label="查看" @click="() => $parent.$emit('view', props.row)" />
                    <q-btn size="sm" color="negative" label="删除" @click="() => $parent.$emit('delete', props.row)" class="q-ml-sm" />
                </q-td>
            ''')
            
            def handle_view(e):
                bom_id = e.args['id']
                details = get_bom_details(bom_id)
                show_view_bom_dialog(bom_id, details)
            table.on('view', handle_view)
            
            def handle_delete(e):
                delete_boms([e.args['id']])
                ui.notify('已删除', type='positive')
                load_table()
            table.on('delete', handle_delete)

    load_table()
