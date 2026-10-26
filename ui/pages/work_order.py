import pandas as pd
from nicegui import ui
from core.services import get_wos, auto_fill_excess_inventory, calculate_loss
from ui.components import show_wo_dialog
from core.utils import export_to_csv

def render_work_order_page():
    state = {'page': 1, 'total': 0, 'size': 20}

    def export_data():
        records, _ = get_wos(1, 10000)
        rows = [{'工单号': r[0].wo_number, '线体': r[0].line, '成品料号': r[0].product_number, '成品名称': r[0].product_name, '计划数量': r[0].plan_qty, '生产日期': r[0].produce_date, '已入库': r[1], '未入库': max(0, r[0].plan_qty - r[1]), '状态': r[0].status} for r in records]
        df = pd.DataFrame(rows)
        export_to_csv(df, 'wo_export.csv')

    with ui.row().classes('w-full justify-between items-center mb-4 border-b pb-4'):
        ui.label('工单管理').classes('text-2xl font-bold')
        with ui.row():
            ui.button('导出 CSV', icon='download', on_click=export_data).classes('bg-gray-600 text-white').props('dense')
            ui.button('新增工单', icon='add', on_click=lambda: show_wo_dialog(load_table)).classes('bg-blue-600 text-white').props('dense')

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
        records, total = get_wos(state['page'], state['size'])
        state['total'] = total
        page_label.set_text(f'第 {state["page"]} / {max(1, (total + 19) // 20)} 页 (共 {total} 条)')
        
        rows = []
        for r in records:
            wo, finished = r[0], r[1]
            remain = max(0, wo.plan_qty - finished)
            rows.append({
                '工单号': wo.wo_number, '线体': wo.line, '成品料号': wo.product_number, 
                '成品名称': wo.product_name, '计划数量': wo.plan_qty, 
                '生产日期': getattr(wo, 'produce_date', ''),
                '已入库': finished, '未入库': remain, '状态': wo.status
            })
        
        with table_container:
            table = ui.table(columns=[
                {'name': '工单号', 'label': '工单号', 'field': '工单号'},
                {'name': '线体', 'label': '线体', 'field': '线体'},
                {'name': '成品料号', 'label': '成品料号', 'field': '成品料号'},
                {'name': '成品名称', 'label': '成品名称', 'field': '成品名称'},
                {'name': '计划数量', 'label': '计划数量', 'field': '计划数量'},
                {'name': '生产日期', 'label': '生产日期', 'field': '生产日期'},
                {'name': '已入库', 'label': '已入库', 'field': '已入库'},
                {'name': '未入库', 'label': '未入库', 'field': '未入库'},
                {'name': '状态', 'label': '状态', 'field': '状态'},
                {'name': '损耗', 'label': '损耗', 'field': '损耗'},
                {'name': '操作', 'label': '操作', 'field': '操作'},
            ], rows=rows).classes('w-full shadow-sm border rounded').props('flat bordered')
            
            table.add_slot('body-cell-损耗', '''
                <q-td :props="props">
                    <q-btn size="sm" color="orange" label="查看损耗" @click="() => $parent.$emit('loss', props.row)" />
                </q-td>
            ''')
            table.add_slot('body-cell-操作', '''
                <q-td :props="props">
                    <q-btn v-if="props.row['状态'] !== '已完成'" size="sm" color="primary" label="修改" @click="() => $parent.$emit('edit', props.row)" />
                    <q-btn v-else size="sm" color="grey" label="不可修改" disable />
                </q-td>
            ''')
            
            def handle_edit(e):
                row = e.args
                db_record = next((r[0] for r in records if r[0].wo_number == row['工单号']), None)
                if db_record: show_wo_dialog(load_table, db_record)
            table.on('edit', handle_edit)

            def show_loss(e):
                wo_number = e.args['工单号']
                data = calculate_loss(wo_number)
                
                formatted_data = [{'序号': i+1, '物料料号': r.get('物料料号', ''), '需求数量': r.get('需求数量', 0), '领料数量': r.get('领料数量', 0), '退料数量': r.get('退料数量', 0), '损耗数量': r.get('损耗数量', 0)} for i, r in enumerate(data)]
                
                with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl'):
                    with ui.row().classes('w-full justify-between items-center mb-4'):
                        ui.label(f'工单 {wo_number} 损耗明细').classes('text-lg font-bold')
                        
                        def export_loss():
                            df = pd.DataFrame(data)
                            df.insert(0, '序号', range(1, len(df) + 1))
                            export_to_csv(df, f'{wo_number}_loss.csv')
                            
                        ui.button('导出 CSV', icon='download', on_click=export_loss).classes('bg-blue-600 text-white').props('dense')
                    
                    table = ui.table(columns=[
                        {'name': '序号', 'label': '序号', 'field': '序号', 'align': 'center'},
                        {'name': '物料料号', 'label': '物料料号', 'field': '物料料号'},
                        {'name': '需求数量', 'label': '需求数量', 'field': '需求数量'},
                        {'name': '领料数量', 'label': '领料数量', 'field': '领料数量'},
                        {'name': '退料数量', 'label': '退料数量', 'field': '退料数量'},
                        {'name': '损耗数量', 'label': '损耗数量', 'field': '损耗数量'},
                    ], rows=formatted_data).classes('w-full shadow-sm border')
                    table.add_slot('body-cell-损耗数量', '''
                        <q-td :props="props" :style="props.value < 0 ? 'color: red; font-weight: bold;' : 'color: green;'">
                            {{ props.value > 0 ? '+' : '' }}{{ props.value }}
                        </q-td>
                    ''')
                    ui.button('关闭', on_click=dialog.close).classes('mt-4 self-end bg-gray-500 text-white')
                dialog.open()
            table.on('loss', show_loss)

        auto_fill_excess_inventory()

    load_table()
