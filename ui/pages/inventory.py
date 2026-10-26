from nicegui import ui
from core.database import SessionLocal
from core.models import Inventory

def render_inventory_page():
    ui.label('库存查询').classes('text-2xl font-bold mb-4')
    db = SessionLocal()
    try:
        records = db.query(Inventory).all()
        rows = [{'料号': r.part_number, '数量': r.quantity, '库位': r.location} for r in records]
        ui.table(columns=[
            {'name': '料号', 'label': '物料料号', 'field': '料号'},
            {'name': '数量', 'label': '当前库存', 'field': '数量'},
            {'name': '库位', 'label': '库位', 'field': '库位'},
        ], rows=rows).classes('w-full shadow-sm border')
    finally:
        db.close()
