import pandas as pd
from nicegui import ui
from core.services import get_issue_details, get_return_details
from core.utils import export_to_csv

def render_records_page(title, btn_text, btn_color, open_dialog_func, get_data_func):
    state = {'page': 1, 'total': 0, 'size': 20}

    def export_data():
        records, _ = get_data_func(1, 10000)
        rows = []
        for r in records:
            if hasattr(r, 'issue_no'): rows.append({'单号': r.issue_no, '工单号': r.wo_number, '总数': r.total_qty, '操作人': r.operator})
            elif hasattr(r, 'return_no'): rows.append({'单号': r.return_no, '工单号': r.wo_number, '总数': r.total_qty, '操作人': r.operator})
            elif hasattr(r, 'finish_no'): rows.append({'单号': r.finish_no, '工单号': r.wo_number, '成品料号': r.product_number, '成品名称': r.product_name, '总数': r.total_qty, '操作人': r.operator})
        
        df = pd.DataFrame(rows)
        export_to_csv(df, f'{title}.csv')

    with ui.row().classes('w-full justify-between items-center mb-4 border-b pb-4'):
        ui.label(title).classes('text-2xl font-bold')
        with ui.row():
            ui.button('导出 CSV', icon='download', on_click=export_data).classes('bg-gray-600 text-white').props('dense')
            ui.button(btn_text, icon='add', on_click=lambda: open_dialog_func(load_table)).classes(btn_color).props('dense')

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
        records, total = get_data_func(state['page'], state['size'])
        state['total'] = total
        page_label.set_text(f'第 {state["page"]} / {max(1, (total + 19) // 20)} 页 (共 {total} 条)')
        
        rows = []
        for r in records:
            if hasattr(r, 'issue_no'): rows.append({'单号': r.issue_no, '工单号': r.wo_number, '总数': r.total_qty, '操作人': r.operator})
            elif hasattr(r, 'return_no'): rows.append({'单号': r.return_no, '工单号': r.wo_number, '总数': r.total_qty, '操作人': r.operator})
            elif hasattr(r, 'finish_no'): rows.append({'单号': r.finish_no, '工单号': r.wo_number, '成品料号': r.product_number, '成品名称': r.product_name, '总数': r.total_qty, '操作人': r.operator})
                
        with table_container:
            cols = [{'name': '单号', 'label': '单据编号', 'field': '单号'}, {'name': '工单号', 'label': '工单号', 'field': '工单号'}]
            if records and hasattr(records[0], 'finish_no'):
                cols += [{'name': '成品料号', 'label': '成品料号', 'field': '成品料号'}, {'name': '成品名称', 'label': '成品名称', 'field': '成品名称'}]
            cols += [{'name': '总数', 'label': '操作总数', 'field': '总数'}, {'name': '操作人', 'label': '操作人', 'field': '操作人'}]
            
            if title in ["生产领料记录", "生产退料记录"]:
                cols.append({'name': '操作', 'label': '操作', 'field': '操作'})

            table = ui.table(columns=cols, rows=rows).classes('w-full shadow-sm border rounded')
            
            if title in ["生产领料记录", "生产退料记录"]:
                table.add_slot('body-cell-操作', '''
                    <q-td :props="props">
                        <q-btn size="sm" color="primary" label="详情" @click="() => $parent.$emit('detail', props.row)" />
                    </q-td>
                ''')
                
                def show_detail(e):
                    doc_no = e.args['单号']
                    if title == "生产领料记录":
                        details = get_issue_details(doc_no)
                    else:
                        details = get_return_details(doc_no)
                        
                    with ui.dialog() as dialog, ui.card().classes('w-[600px]'):
                        ui.label(f'单据 {doc_no} 明细').classes('text-lg font-bold mb-4')
                        ui.table(columns=[
                            {'name': '物料料号', 'label': '物料料号', 'field': '物料料号'},
                            {'name': '数量', 'label': '数量', 'field': '数量'},
                            {'name': '所属工单', 'label': '所属工单', 'field': '所属工单'},
                        ], rows=details).classes('w-full shadow-sm border')
                        ui.button('关闭', on_click=dialog.close).classes('mt-4 self-end bg-gray-500 text-white')
                    dialog.open()
                table.on('detail', show_detail)

    load_table()
