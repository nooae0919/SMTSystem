import pandas as pd
from nicegui import ui, events
from core.services import get_parts, add_part
from core.database import SessionLocal
from core.models import Part
from ui.components import handle_upload
from core.utils import export_to_csv

def render_part_page():
    state = {'page': 1, 'total': 0, 'size': 20, 'keyword': ''}

    async def import_data(e: events.UploadEventArguments):
        try:
            data = await handle_upload(e)
            db = SessionLocal()
            for r in data:
                part_no = r.get('物料料号') or r.get('料号') or r.get('part_number')
                part_name = r.get('物料名称') or r.get('名称') or r.get('part_name')
                part_desc = r.get('物料描述') or r.get('描述') or r.get('description')
                if not part_no: continue
                
                existing = db.query(Part).filter_by(part_number=part_no).first()
                if existing:
                    existing.part_name = part_name
                    existing.description = part_desc
                else:
                    db.add(Part(part_number=part_no, part_name=part_name, description=part_desc))
            db.commit()
            db.close()
            ui.notify('CSV 导入成功', type='positive')
            ui.timer(0.1, load_table, once=True)
        except Exception as ex:
            ui.notify(f'导入失败: {ex}', type='negative')

    def export_data():
        records, _ = get_parts(1, 10000)
        rows = [{'物料料号': r.part_number, '物料名称': r.part_name, '物料描述': getattr(r, 'description', '')} for r in records]
        df = pd.DataFrame(rows)
        export_to_csv(df, 'part_export.csv')

    with ui.row().classes('w-full justify-between items-center mb-6 border-b pb-4'):
        ui.label('物料信息').classes('text-2xl font-bold text-gray-800')
        
        with ui.row().classes('items-center gap-4'):
            with ui.row().classes('items-center gap-2 bg-gray-50 px-2 py-1 rounded-lg'):
                kw_input = ui.input('按物料料号搜索').classes('w-48').props('dense outlined').on('keydown.enter', lambda: do_search())
                
                def do_search():
                    state['keyword'] = kw_input.value
                    state['page'] = 1
                    load_table()

                ui.button('搜索', icon='search', on_click=do_search).classes('bg-green-600 text-white px-4').props('dense rounded')

            with ui.row().classes('items-center gap-2'):
                upload = ui.upload(on_upload=import_data, auto_upload=True).props('flat accept=.csv').classes('hidden')
                ui.button('导入 CSV', icon='upload', on_click=lambda: upload.run_method('pickFiles')).classes('bg-blue-600 text-white').props('dense')
                ui.button('导出 CSV', icon='download', on_click=export_data).classes('bg-gray-600 text-white').props('dense')
                
                def show_add_dialog():
                    with ui.dialog() as dialog, ui.card().classes('w-96'):
                        ui.label('新增物料信息').classes('text-lg font-bold')
                        pn = ui.input('物料料号').classes('w-full')
                        name = ui.input('物料名称').classes('w-full')
                        desc = ui.input('物料描述').classes('w-full')
                        def save():
                            if not pn.value: return ui.notify('料号不能为空', type='warning')
                            add_part(pn.value, name.value, desc.value, '')
                            ui.notify('保存成功', type='positive')
                            dialog.close()
                            do_search()
                        with ui.row().classes('w-full justify-end mt-4'):
                            ui.button('取消', on_click=dialog.close).props('flat')
                            ui.button('保存', on_click=save).classes('bg-blue-600')
                    dialog.open()
                    
                ui.button('新增物料', icon='add', on_click=show_add_dialog).classes('bg-teal-600 text-white').props('dense')

    table_container = ui.column().classes('w-full')
    
    with ui.row().classes('w-full justify-end items-center mt-4'):
        ui.button(icon='chevron_left', on_click=lambda: change_page(-1)).props('flat')
        page_label = ui.label('第 1 页').classes('mx-2 text-gray-600')
        ui.button(icon='chevron_right', on_click=lambda: change_page(1)).props('flat')

    def change_page(delta):
        max_pages = max(1, (state['total'] + state['size'] - 1) // state['size'])
        new_page = state['page'] + delta
        if 1 <= new_page <= max_pages:
            state['page'] = new_page
            load_table()

    def load_table():
        table_container.clear()
        records, total = get_parts(state['page'], state['size'], state['keyword'])
        state['total'] = total
        page_label.set_text(f'第 {state["page"]} / {max(1, (total + 19) // 20)} 页 (共 {total} 条)')
        
        rows = [{'料号': r.part_number, '名称': r.part_name, '描述': getattr(r, 'description', '')} for r in records]
        
        with table_container:
            ui.table(columns=[
                {'name': '料号', 'label': '物料料号', 'field': '料号', 'align': 'left'},
                {'name': '名称', 'label': '物料名称', 'field': '名称', 'align': 'left'},
                {'name': '描述', 'label': '物料描述', 'field': '描述', 'align': 'left'},
            ], rows=rows).classes('w-full shadow-sm border rounded').props('flat bordered')

    load_table()
