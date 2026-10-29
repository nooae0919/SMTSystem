import pandas as pd
from io import BytesIO
from nicegui import ui, events
from core.services import (
    create_wo_with_snapshot, add_part, submit_issue,
    submit_return, submit_finish, create_bom_with_details,
    update_wo, get_unfinished_wos, get_bom_headers, rebuild_wo_snapshot,
)
from core.utils import export_to_csv


# ==================== 通用工具 ====================
async def handle_upload(e: events.UploadEventArguments):
    file_content = await e.file.read()
    try:
        csv_text = file_content.decode("utf-8-sig")
        file_stream = BytesIO(csv_text.encode("utf-8"))
        df = pd.read_csv(file_stream)
    except UnicodeDecodeError:
        csv_text = file_content.decode("gbk")
        file_stream = BytesIO(csv_text.encode("utf-8"))
        df = pd.read_csv(file_stream)
    df = df.fillna("")
    return df.to_dict("records")


# ==================== 物料 ====================
def show_add_part_dialog(refresh_callback):
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("新增物料信息").classes("text-lg font-bold")
        pn = ui.input("物料料号").classes("w-full")
        name = ui.input("物料名称").classes("w-full")
        desc = ui.input("物料描述").classes("w-full")

        def save():
            if not pn.value:
                return ui.notify("料号不能为空", type="warning")
            try:
                add_part(pn.value, name.value, desc.value, "")
                ui.notify("保存成功", type="positive")
                dialog.close()
                refresh_callback()
            except Exception as e:
                ui.notify(f"失败: {e}", type="negative")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("取消", on_click=dialog.close).props("flat")
            ui.button("保存", on_click=save).classes("bg-blue-600")
    dialog.open()


# ==================== BOM ====================
def show_add_bom_dialog(refresh_callback):
    with ui.dialog() as dialog, ui.card().classes("w-[700px]"):
        ui.label("新增 BOM 表").classes("text-lg font-bold")
        with ui.row().classes("w-full"):
            prod_no = ui.input("成品料号").classes("flex-grow")
            version = ui.input("版本号", value="V1").classes("w-24")
        prod_name = ui.input("成品名称").classes("w-full")
        items_ui = ui.column().classes("w-full mt-4 max-h-64 overflow-auto border p-2")

        def add_row(data=None):
            with items_ui:
                with ui.row().classes("w-full items-center gap-2 flex-nowrap") as row:
                    ui.input("子件料号",
                             value=data.get("子件料号", "") if data else "").classes("flex-grow")
                    # 移除 validation，统一高度，完美对齐
                    ui.input("基础用量", value="" if not data else str(data.get("基础用量", ""))).classes("w-24")
                    ui.space()
                    ui.button(icon="delete", on_click=row.delete).props("flat color=red")

        add_row()

        async def on_upload(e):
            try:
                for r in await handle_upload(e):
                    add_row({
                        "子件料号": r.get("子件料号") or r.get("物料料号"),
                        "基础用量": r.get("基础用量") or r.get("数量"),
                    })
                ui.notify("CSV 导入成功", type="positive")
            except Exception as ex:
                ui.notify(f"失败: {ex}", type="negative")

        def download_template():
            df = pd.DataFrame([{"子件料号": "M-001", "基础用量": 2}])
            export_to_csv(df, "bom_template.csv")

        with ui.row().classes("w-full mt-2 items-center justify-between"):
            ui.button("+ 添加子件", on_click=add_row).props("flat")
            with ui.row().classes("gap-2"):
                ui.button("下载导入模板", icon="download", on_click=download_template) \
                    .props("flat color=blue")
                ui.upload(on_upload=on_upload, auto_upload=True) \
                    .props('flat accept=.csv label="导入 CSV"')

        def save():
            valid_items = []
            for row in items_ui.default_slot.children:
                inputs = row.default_slot.children
                if len(inputs) >= 2 and inputs[0].value:
                    try:
                        qty_val = float(inputs[1].value) if inputs[1].value else 0.0
                    except ValueError:
                        return ui.notify("基础用量必须是有效的数字", type="warning")

                    if qty_val > 0:
                        valid_items.append({
                            "part_number": inputs[0].value,
                            "qty_per_board": qty_val,
                        })
            if not valid_items:
                return ui.notify("请至少添加一条有效的子件明细（用量需大于0）", type="warning")
            try:
                create_bom_with_details(prod_no.value, prod_name.value,
                                        version.value, valid_items)
                ui.notify("保存成功", type="positive")
                dialog.close()
                refresh_callback()
            except Exception as e:
                ui.notify(str(e), type="negative")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("取消", on_click=dialog.close).props("flat")
            ui.button("保存 BOM", on_click=save).classes("bg-blue-600")
    dialog.open()


def show_view_bom_dialog(bom_data):
    if not bom_data:
        return
    header = bom_data["header"]
    details = bom_data["details"]

    with ui.dialog() as dialog, ui.card().classes("w-[700px]"):
        with ui.column().classes("w-full mb-4 bg-gray-50 p-4 rounded border"):
            with ui.row().classes("w-full justify-between"):
                ui.label(f"成品料号: {header.product_number}") \
                    .classes("text-lg font-bold text-blue-600")
                ui.label(f"成品名称: {header.product_name}") \
                    .classes("text-lg font-bold text-blue-600")
                ui.label(f"版本号: {header.version}") \
                    .classes("text-lg font-bold text-blue-600")

        rows = [{
            "序号": i + 1,
            "子件料号": d["part_number"],
            "子件名称": d["part_name"],
            "基础用量": d["qty_per_board"],
        } for i, d in enumerate(details)]

        ui.table(columns=[
            {"name": "序号", "label": "序号", "field": "序号", "align": "center", "style": "width: 60px"},
            {"name": "子件料号", "label": "子件料号", "field": "子件料号"},
            {"name": "子件名称", "label": "子件名称", "field": "子件名称"},
            {"name": "基础用量", "label": "基础用量", "field": "基础用量"},
        ], rows=rows).classes("w-full shadow-sm border")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("关闭", on_click=dialog.close) \
                .classes("bg-gray-500 text-white")
    dialog.open()


# ==================== 工单 ====================
def show_wo_dialog(refresh_callback, wo_data=None):
    with ui.dialog() as dialog, ui.card().classes("w-[400px]"):
        ui.label("编辑工单" if wo_data else "新增工单") \
            .classes("text-lg font-bold mb-4")

        wo_no = ui.input("工单号",
                         value=wo_data.wo_number if wo_data else "").classes("w-full")
        line = ui.select(["1线", "2线"], label="生产线",
                         value=wo_data.line if wo_data else "1线").classes("w-full")

        if not wo_data:
            boms, _ = get_bom_headers(1, 5000)
            bom_options = {
                b.id: f"{b.product_number} | {b.product_name} | {b.version}"
                for b in boms
            }
            bom_select = ui.select(bom_options, label="选择 BOM 自动带出成品") \
                .classes("w-full")
            prod_no_input = ui.input("成品料号").props("readonly") \
                .classes("w-full hidden")
            prod_name_input = ui.input("成品名称").props("readonly") \
                .classes("w-full hidden")

            def on_bom_select(e):
                if e.value:
                    b = next((x for x in boms if x.id == e.value), None)
                    if b:
                        prod_no_input.value = b.product_number
                        prod_name_input.value = b.product_name
            bom_select.on_value_change(on_bom_select)
        else:
            bom_select = None
            prod_no_input = ui.input("成品料号", value=wo_data.product_number) \
                .props("readonly").classes("w-full")
            prod_name_input = ui.input("成品名称", value=wo_data.product_name) \
                .props("readonly").classes("w-full")

        plan_qty = ui.input("计划数量", value=str(wo_data.plan_qty) if wo_data else "").classes("w-full")
            
        produce_date = ui.input("计划生产日期",
                                value=wo_data.produce_date if wo_data else "") \
            .classes("w-full").props("type=date")

        if wo_data:
            status = ui.select(
                ["待生产", "生产中"], label="状态",
                value=wo_data.status if wo_data.status != "已完成" else "生产中",
            ).classes("w-full")
            if wo_data.status == "已完成":
                status.props("readonly")
                status.classes("disabled")

            def do_refresh():
                try:
                    rebuild_wo_snapshot(wo_data.wo_number)
                    ui.notify("BOM 快照已更新！", type="positive")
                except Exception as e:
                    ui.notify(f"更新失败: {e}", type="negative")

            ui.button("刷新 BOM 快照", icon="sync", on_click=do_refresh) \
                .classes("w-full mt-2 bg-orange-500 text-white").props("dense")
        else:
            status = ui.select(["待生产", "生产中"], label="状态", value="待生产") \
                .classes("w-full")

        def save():
            try:
                plan_qty_val = int(plan_qty.value) if plan_qty.value else 0
            except ValueError:
                return ui.notify("计划数量必须是有效的数字", type="warning")

            if plan_qty_val <= 0:
                return ui.notify("计划数量必须大于0", type="warning")

            try:
                if wo_data:
                    update_wo(wo_no.value, line.value, plan_qty_val,
                              produce_date.value, status.value)
                else:
                    if not bom_select.value:
                        return ui.notify("请先选择 BOM", type="warning")
                    create_wo_with_snapshot(
                        wo_no.value, line.value,
                        prod_no_input.value, prod_name_input.value,
                        plan_qty_val, produce_date.value,
                        bom_select.value, status.value,
                    )
                ui.notify("操作成功", type="positive")
                dialog.close()
                refresh_callback()
            except Exception as e:
                ui.notify(str(e), type="negative")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("取消", on_click=dialog.close).props("flat")
            ui.button("保存", on_click=save).classes("bg-blue-600")
    dialog.open()


# ==================== 领料 / 退料（共用实现） ====================
def _show_transaction_dialog(refresh_callback, title, label, btn_text,
                             btn_color, submit_func, qty_key, default_qty):
    with ui.dialog() as dialog, ui.card().classes("w-[800px]"):
        ui.label(title).classes("text-lg font-bold")
        ui.label("物料明细 (每行需填工单号)") \
            .classes("text-sm text-gray-500 mt-2")
        items_ui = ui.column().classes("w-full max-h-64 overflow-auto border p-2")

        def add_row(data=None):
            with items_ui:
                with ui.row().classes("w-full items-center gap-2 flex-nowrap") as row:
                    ui.input("物料料号",
                             value=data.get("物料料号", "") if data else "") \
                        .classes("w-48")
                    # 同样移除 validation
                    ui.input("数量", value="" if not data else str(data.get("物料数量", ""))) \
                        .classes("w-24")
                    ui.input("工单号",
                             value=data.get("工单号", "") if data else "") \
                        .classes("w-48")
                    ui.space()
                    ui.button(icon="delete", on_click=row.delete) \
                        .props("flat color=red")
        add_row()

        def download_template():
            df = pd.DataFrame([{
                "物料料号": "M-001",
                "物料数量": default_qty,
                "工单号": "WO-001",
            }])
            export_to_csv(df, f"{label}_template.csv")

        async def on_upload(e):
            try:
                for r in await handle_upload(e):
                    add_row({
                        "物料料号": r.get("物料料号"),
                        "物料数量": r.get("物料数量"),
                        "工单号": r.get("工单号"),
                    })
                ui.notify("CSV 导入成功", type="positive")
            except Exception as ex:
                ui.notify(f"失败: {ex}", type="negative")

        with ui.row().classes("w-full mt-2 items-center justify-between"):
            ui.button("+ 添加一行", on_click=add_row).props("flat")
            with ui.row().classes("gap-2"):
                ui.button("下载模板", icon="download", on_click=download_template) \
                    .props("flat color=blue")
                ui.upload(on_upload=on_upload, auto_upload=True) \
                    .props('flat accept=.csv label="导入 CSV"')

        operator = ui.input("操作人", value="操作员A").classes("w-full mt-4")

        def save():
            valid = []
            for r in items_ui.default_slot.children:
                inputs = r.default_slot.children
                if len(inputs) >= 3 and inputs[0].value and inputs[2].value:
                    try:
                        qty_val = int(inputs[1].value) if inputs[1].value else 0
                    except ValueError:
                        return ui.notify("数量必须是有效的整数", type="warning")

                    if qty_val > 0:
                        valid.append({
                            "part_number": inputs[0].value,
                            qty_key: qty_val,
                            "wo_number": inputs[2].value,
                        })
            if not valid:
                return ui.notify("请填写完整明细（含有效数量与工单号）", type="warning")
            try:
                submit_func(operator.value, valid)
                ui.notify(f"{label}成功", type="positive")
                dialog.close()
                refresh_callback()
            except Exception as e:
                ui.notify(str(e), type="negative")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("取消", on_click=dialog.close).props("flat")
            ui.button(btn_text, on_click=save).classes(btn_color)
    dialog.open()


def show_issue_dialog(refresh_callback):
    _show_transaction_dialog(
        refresh_callback,
        title="新建领料", label="领料",
        btn_text="提交", btn_color="bg-green-600",
        submit_func=submit_issue, qty_key="issue_qty", default_qty=100,
    )


def show_return_dialog(refresh_callback):
    _show_transaction_dialog(
        refresh_callback,
        title="新建退料", label="退料",
        btn_text="提交", btn_color="bg-orange-600",
        submit_func=submit_return, qty_key="return_qty", default_qty=1,
    )


# ==================== 成品入库 ====================
def show_finish_dialog(refresh_callback):
    with ui.dialog() as dialog, ui.card().classes("w-96"):
        ui.label("成品入库").classes("text-lg font-bold")
        wos = get_unfinished_wos()
        wo_options = {
            w.wo_number: f"{w.wo_number} | {w.product_number}"
            for w in wos
        }

        wo_select = ui.select(wo_options, label="选择工单(必填)").classes("w-full")
        prod_no = ui.input("成品料号").props("readonly").classes("w-full")
        prod_name = ui.input("成品名称").props("readonly").classes("w-full")
        
        qty = ui.input("本次入库数量", value="").classes("w-full")
        operator = ui.input("入库人", value="操作员A").classes("w-full")

        def on_wo_change():
            if wo_select.value:
                wo = next((w for w in wos if w.wo_number == wo_select.value), None)
                if wo:
                    prod_no.value = wo.product_number
                    prod_name.value = wo.product_name
        wo_select.on_value_change(on_wo_change)

        def save():
            if not wo_select.value:
                return ui.notify("请选择工单", type="warning")
            
            try:
                qty_val = int(qty.value) if qty.value else 0
            except ValueError:
                return ui.notify("入库数量必须是有效的整数", type="warning")
                
            if qty_val <= 0:
                return ui.notify("请输入有效的入库数量", type="warning")

            try:
                submit_finish(wo_select.value, prod_no.value,
                              prod_name.value, qty_val, operator.value)
                ui.notify("入库成功", type="positive")
                dialog.close()
                refresh_callback()
            except Exception as e:
                ui.notify(str(e), type="negative")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("取消", on_click=dialog.close).props("flat")
            ui.button("确认入库", on_click=save).classes("bg-purple-600")
    dialog.open()
