import pandas as pd
from nicegui import ui, events

from core.services import get_inventory, delete_inventory_items, sync_all_excess_records
from core.database import SessionLocal
from core.models import Inventory
from ui.components import handle_upload
from core.utils import export_to_csv


def render_inventory_page():
    sync_all_excess_records()
    state = {"page": 1, "total": 0, "size": 20, "keyword": "", "type": "料号"}

    async def import_data(e: events.UploadEventArguments):
        db = SessionLocal()
        try:
            data = await handle_upload(e)
            for r in data:
                part_no = r.get("物料料号") or r.get("料号")
                part_name = r.get("物料名称") or r.get("名称")
                qty = r.get("库存数量") or r.get("数量") or 0
                loc = r.get("库位") or ""
                if not part_no:
                    continue
                db.add(Inventory(
                    part_number=part_no, part_name=part_name,
                    quantity=int(qty), location=loc, source="手动导入",
                ))
            db.commit()
            ui.notify("CSV 导入成功", type="positive")
            ui.timer(0.1, load_table, once=True)
        except Exception as ex:
            db.rollback()
            ui.notify(f"导入失败: {ex}", type="negative")
        finally:
            db.close()

    def export_data():
        records, _ = get_inventory(1, 10000, state["keyword"], state["type"])
        # 导出时也去掉“数据类别”
        rows = [{
            "物料料号": r["part_number"],
            "物料名称": r["part_name"], 
            "库存数量": r["quantity"],
            "库位": r["location"], 
            "来源": r["source"],
        } for r in records]
        export_to_csv(pd.DataFrame(rows), "inventory_export.csv")

    with ui.row().classes("w-full justify-between items-center mb-4 border-b pb-4"):
        ui.label("库存管理").classes("text-2xl font-bold text-gray-800")

        with ui.row().classes("items-center gap-4"):
            with ui.row().classes("items-center gap-2 bg-gray-50 px-2 py-1 rounded-lg"):
                type_select = ui.select(["料号", "库位"], value="料号") \
                    .classes("w-24").props("dense outlined")
                kw_input = ui.input("搜索关键字").classes("w-48").props("dense outlined") \
                    .on("keydown.enter", lambda: do_search())

                def do_search():
                    state["type"] = type_select.value
                    state["keyword"] = kw_input.value
                    state["page"] = 1
                    load_table()

                ui.button("搜索", icon="search", on_click=do_search) \
                    .classes("bg-green-600 text-white px-4").props("dense rounded")

            with ui.row().classes("items-center gap-2"):
                upload = ui.upload(on_upload=import_data, auto_upload=True) \
                    .props("flat accept=.csv").classes("hidden")
                ui.button("导入 CSV", icon="upload",
                          on_click=lambda: upload.run_method("pickFiles")) \
                    .classes("bg-blue-600 text-white").props("dense")
                ui.button("导出 CSV", icon="download", on_click=export_data) \
                    .classes("bg-gray-600 text-white").props("dense")

    table_container = ui.column().classes("w-full")

    with ui.row().classes("w-full justify-between items-center mt-4"):
        btn_batch_delete = ui.button(
            "批量删除", icon="delete", on_click=lambda: confirm_delete()
        ).classes("bg-red-600 text-white hidden")

        with ui.row().classes("items-center"):
            def prev_page():
                if state["page"] > 1:
                    state["page"] -= 1
                    load_table()

            def next_page():
                max_pages = max(1, (state["total"] + state["size"] - 1) // state["size"])
                if state["page"] < max_pages:
                    state["page"] += 1
                    load_table()

            ui.button(icon="chevron_left", on_click=prev_page).props("flat")
            page_label = ui.label("第 1 页").classes("mx-2 text-gray-600")
            ui.button(icon="chevron_right", on_click=next_page).props("flat")

    def confirm_delete():
        table = table_container.default_slot.children[0]
        selected = table.selected
        if not selected:
            return

        inv_ids = [r["id"] for r in selected if not str(r["id"]).startswith("ex_")]
        ex_count = len(selected) - len(inv_ids)

        if not inv_ids:
            return ui.notify("超发暂存数据由系统自动生成，不可手动删除", type="warning")

        delete_inventory_items(inv_ids)
        ui.notify(f"成功删除 {len(inv_ids)} 条真实库存", type="positive")
        if ex_count > 0:
            ui.notify(f"已忽略 {ex_count} 条超发暂存数据", type="info")

        state["page"] = 1
        load_table()
        btn_batch_delete.classes(add="hidden")

    def load_table():
        table_container.clear()
        
        records, total = get_inventory(
            state["page"], state["size"], state["keyword"], state["type"]
        )
        state["total"] = total

        # 剔除 "类型" 字段
        rows = [{
            "id": r["id"],
            "物料料号": r["part_number"],
            "物料名称": r["part_name"],
            "库存数量": r["quantity"],
            "库位": r["location"],
            "来源": r["source"],
        } for r in records]

        max_pages = max(1, (total + state["size"] - 1) // state["size"])
        page_label.set_text(f'第 {state["page"]} / {max_pages} 页 (共 {total} 条)')

        with table_container:
            # 剔除 "数据类别" 列定义
            table = ui.table(
                columns=[
                    {"name": "物料料号", "label": "物料料号", "field": "物料料号", "align": "left"},
                    {"name": "物料名称", "label": "物料名称", "field": "物料名称", "align": "left"},
                    {"name": "库存数量", "label": "库存/暂存数", "field": "库存数量", "align": "left"},
                    {"name": "库位", "label": "库位(线体)", "field": "库位", "align": "left"},
                    {"name": "来源", "label": "来源", "field": "来源", "align": "left"},
                ],
                rows=rows, row_key="id", selection="multiple",
            ).classes("w-full shadow-sm border rounded").props("flat bordered")

            def on_select(e):
                if e.args:
                    btn_batch_delete.classes(remove="hidden")
                else:
                    btn_batch_delete.classes(add="hidden")
            table.on("selection", on_select)

    load_table()
