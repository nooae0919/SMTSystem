from contextlib import contextmanager

from sqlalchemy import text, func

from core.database import SessionLocal
from core.models import *
from datetime import datetime


@contextmanager
def get_db():
    """统一管理 Session 生命周期，出错自动回滚。"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ==================== 1. 工单管理 ====================
def get_wos(page, size):
    with get_db() as db:
        total = db.query(WorkOrder).count()

        records = (
            db.query(
                WorkOrder,
                func.coalesce(func.sum(FinishHeader.total_qty), 0).label("finished_qty"),
            )
            .outerjoin(FinishHeader, WorkOrder.wo_number == FinishHeader.wo_number)
            .group_by(WorkOrder.id)
            .order_by(WorkOrder.id.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        return records, total


def create_wo_with_snapshot(wo_no, line, prod_no, prod_name, qty,
                            produce_date, bom_id, status="待生产"):
    with get_db() as db:
        bom_head = db.query(BOM_Header).filter_by(id=bom_id).first()
        if not bom_head:
            raise ValueError("找不到该 BOM 数据")

        db.add(WorkOrder(
            wo_number=wo_no, line=line, product_number=prod_no,
            product_name=prod_name, plan_qty=qty, produce_date=produce_date,
            status=status, bom_version=bom_head.version,
        ))

        for d in db.query(BOM_Detail).filter_by(bom_id=bom_id).all():
            db.add(WOBomSnapshot(
                wo_number=wo_no, part_number=d.part_number,
                qty_per_board=d.qty_per_board,
            ))

        db.commit()
    # 新工单没有任何领料，无需同步（保留也无害，但去掉可省一次事务）
    # sync_single_wo_excess(wo_no)


def update_wo(wo_number, line, qty, produce_date, status):
    with get_db() as db:
        wo = db.query(WorkOrder).filter_by(wo_number=wo_number).first()
        if wo:
            wo.line = line
            wo.plan_qty = qty
            wo.produce_date = produce_date
            wo.status = status
            db.commit()
    sync_single_wo_excess(wo_number)


def rebuild_wo_snapshot(wo_number):
    with get_db() as db:
        wo = db.query(WorkOrder).filter_by(wo_number=wo_number).first()
        if not wo:
            return
        bom_head = (
            db.query(BOM_Header)
            .filter_by(product_number=wo.product_number)
            .order_by(BOM_Header.id.desc())
            .first()
        )
        if not bom_head:
            raise ValueError("未找到该成品的 BOM")

        db.query(WOBomSnapshot).filter_by(wo_number=wo_number).delete(
            synchronize_session=False
        )
        for d in db.query(BOM_Detail).filter_by(bom_id=bom_head.id).all():
            db.add(WOBomSnapshot(
                wo_number=wo_number, part_number=d.part_number,
                qty_per_board=d.qty_per_board,
            ))

        wo.bom_version = bom_head.version
        db.commit()
    sync_single_wo_excess(wo_number)


def delete_wos(wo_numbers):
    if not wo_numbers:
        return
    with get_db() as db:
        db.query(WorkOrder).filter(WorkOrder.wo_number.in_(wo_numbers)).delete(
            synchronize_session=False
        )
        db.query(WOBomSnapshot).filter(WOBomSnapshot.wo_number.in_(wo_numbers)).delete(
            synchronize_session=False
        )
        db.query(ExcessRecord).filter(ExcessRecord.wo_number.in_(wo_numbers)).delete(
            synchronize_session=False
        )
        db.commit()


# ==================== 2. BOM 管理 ====================
def get_bom_headers(page, size):
    with get_db() as db:
        q = db.query(BOM_Header).order_by(BOM_Header.id.desc())
        return q.offset((page - 1) * size).limit(size).all(), q.count()


def get_bom_details(bom_id):
    with get_db() as db:
        bom_head = db.query(BOM_Header).filter_by(id=bom_id).first()
        if not bom_head:
            return None

        details = db.query(BOM_Detail).filter_by(bom_id=bom_id).all()
        detail_list = []
        for d in details:
            part = db.query(Part).filter_by(part_number=d.part_number).first()
            detail_list.append({
                "part_number": d.part_number,
                "part_name": part.part_name if part else "",
                "qty_per_board": d.qty_per_board,
            })
        return {"header": bom_head, "details": detail_list}


def delete_boms(bom_ids):
    if not bom_ids:
        return
    with get_db() as db:
        db.query(BOM_Detail).filter(BOM_Detail.bom_id.in_(bom_ids)).delete(
            synchronize_session=False
        )
        db.query(BOM_Header).filter(BOM_Header.id.in_(bom_ids)).delete(
            synchronize_session=False
        )
        db.commit()


def create_bom_with_details(prod_no, prod_name, version, items):
    with get_db() as db:
        bom_head = BOM_Header(
            product_number=prod_no, product_name=prod_name, version=version
        )
        db.add(bom_head)
        db.flush()
        for item in items:
            db.add(BOM_Detail(
                bom_id=bom_head.id,
                part_number=item["part_number"],
                qty_per_board=item["qty_per_board"],
            ))
        db.commit()


def get_bom_export_details(bom_ids):
    if not bom_ids:
        return []
    with get_db() as db:
        sql = text("""
            SELECT h.product_number, h.product_name, h.version,
                   d.part_number, p.part_name, d.qty_per_board
            FROM bom_header h
            JOIN bom_detail d ON h.id = d.bom_id
            LEFT JOIN part p ON d.part_number = p.part_number
            WHERE h.id IN :ids
        """)
        rows = db.execute(sql, {"ids": tuple(bom_ids)}).fetchall()
        return [{
            "成品料号": r[0], "成品名称": r[1], "版本号": r[2],
            "子件料号": r[3], "子件名称": r[4] or "", "基础用量": r[5],
        } for r in rows]


# ==================== 3. 业务单据 ====================
def submit_issue(operator, items):
    with get_db() as db:
        issue_no = f"IS{datetime.now().strftime('%m%d%H%M%S')}"
        total_qty = sum(i["issue_qty"] for i in items)
        first_wo = items[0]["wo_number"] if items else ""
        db.add(IssueHeader(
            issue_no=issue_no, wo_number=first_wo,
            operator=operator, total_qty=total_qty,
        ))

        touched_wos = set()
        for item in items:
            wo_num = item["wo_number"]
            touched_wos.add(wo_num)
            # 用 ORM add 代替 raw INSERT
            db.add(IssueDetail(
                issue_no=issue_no,
                part_number=item["part_number"],
                issue_qty=item["issue_qty"],
                wo_number=wo_num,
            ))

        for wo in touched_wos:
            wo_obj = db.query(WorkOrder).filter_by(wo_number=wo).first()
            if wo_obj and wo_obj.status == "待生产":
                wo_obj.status = "生产中"
        db.commit()

    for wo in touched_wos:
        sync_single_wo_excess(wo)
    return issue_no


def submit_return(operator, items):
    with get_db() as db:
        return_no = f"RT{datetime.now().strftime('%m%d%H%M%S')}"
        total_qty = sum(i["return_qty"] for i in items)
        first_wo = items[0]["wo_number"] if items else ""
        db.add(ReturnHeader(
            return_no=return_no, wo_number=first_wo,
            operator=operator, total_qty=total_qty,
        ))

        touched_wos = set()
        for item in items:
            wo_num = item["wo_number"]
            touched_wos.add(wo_num)
            db.add(ReturnDetail(
                return_no=return_no,
                part_number=item["part_number"],
                return_qty=item["return_qty"],
                wo_number=wo_num,
            ))
        db.commit()

    for wo in touched_wos:
        sync_single_wo_excess(wo)
    return return_no


def submit_finish(wo_number, prod_no, prod_name, finish_qty, operator):
    with get_db() as db:
        finish_no = f"FG{datetime.now().strftime('%m%d%H%M%S')}"
        db.add(FinishHeader(
            finish_no=finish_no, wo_number=wo_number,
            product_number=prod_no, product_name=prod_name,
            total_qty=finish_qty, operator=operator,
        ))

        wo = db.query(WorkOrder).filter_by(wo_number=wo_number).first()
        if wo:
            total_finished = (
                db.query(func.sum(FinishHeader.total_qty))
                .filter_by(wo_number=wo_number)
                .scalar()
                or 0
            )
            total_finished += finish_qty
            if total_finished >= wo.plan_qty:
                wo.status = "已完成"
        db.commit()
    sync_single_wo_excess(wo_number)
    return finish_no


# ==================== 4. 精准超发同步 ====================
def sync_single_wo_excess(wo_number):
    """只针对单个工单重算超发数据。⚠️ 修复：领料 - 退料 - 需求。"""
    with get_db() as db:
        db.query(ExcessRecord).filter_by(wo_number=wo_number).delete(
            synchronize_session=False
        )
        db.commit()

        wo = db.query(WorkOrder).filter_by(wo_number=wo_number).first()
        if not wo or wo.status == "已完成":
            return

        sql = text("""
            SELECT w.wo_number, w.product_name, w.line, s.part_number, p.part_name,
                   (COALESCE((
                       SELECT SUM(issue_qty) FROM issue_detail d
                       JOIN issue_header h ON d.issue_no = h.issue_no
                       WHERE h.wo_number = w.wo_number AND d.part_number = s.part_number
                   ), 0)
                   - COALESCE((
                       SELECT SUM(return_qty) FROM return_detail d
                       JOIN return_header h ON d.return_no = h.return_no
                       WHERE h.wo_number = w.wo_number AND d.part_number = s.part_number
                   ), 0)
                   - CEIL(s.qty_per_board * w.plan_qty)) AS excess_qty
            FROM wo_bom_snapshot s
            JOIN wo w ON s.wo_number = w.wo_number
            LEFT JOIN part p ON s.part_number = p.part_number
            WHERE w.wo_number = :wo
        """)
        results = db.execute(sql, {"wo": wo_number}).fetchall()

        for r in results:
            wo_no, prod_name, line, part_no, part_name, excess = r
            if excess and excess > 0:
                db.add(ExcessRecord(
                    wo_number=wo_no, product_name=prod_name,
                    part_number=part_no, part_name=part_name,
                    quantity=excess, line=line,
                ))
        db.commit()


# ==================== 5. 查询与报表 ====================
def get_issue_list(page, size):
    with get_db() as db:
        q = db.query(IssueHeader).order_by(IssueHeader.id.desc())
        return q.offset((page - 1) * size).limit(size).all(), q.count()


def get_return_list(page, size):
    with get_db() as db:
        q = db.query(ReturnHeader).order_by(ReturnHeader.id.desc())
        return q.offset((page - 1) * size).limit(size).all(), q.count()


def get_finish_list(page, size):
    with get_db() as db:
        q = db.query(FinishHeader).order_by(FinishHeader.id.desc())
        return q.offset((page - 1) * size).limit(size).all(), q.count()


def get_unfinished_wos():
    with get_db() as db:
        return db.query(WorkOrder).filter(WorkOrder.status != "已完成").all()


def get_inventory(page, size, keyword="", search_type="料号"):
    """
    统一视图：物理库存 + 超发暂存。
    返回 (list[dict], total)。⚠️ 修复 SQL 注入；一次查询即可拿到全部数据。
    """
    with get_db() as db:
        union_sql = """
            SELECT CAST(id AS TEXT) AS id, '真实库存' AS data_type,
                   part_number, part_name, quantity, location, source
            FROM inventory
            UNION ALL
            SELECT 'ex_' || CAST(id AS TEXT) AS id, '超发暂存' AS data_type,
                   part_number, part_name, quantity, line AS location, product_name AS source
            FROM excess_record
        """

        params = {}
        where_clause = ""
        if keyword:
            if search_type == "料号":
                where_clause = "WHERE part_number LIKE :kw"
            else:
                where_clause = "WHERE location LIKE :kw"
            params["kw"] = f"%{keyword}%"

        total = db.execute(
            text(f"SELECT COUNT(*) FROM ({union_sql}) t {where_clause}"), params
        ).scalar() or 0

        params["limit"] = size
        params["offset"] = (page - 1) * size
        rows = db.execute(
            text(f"""
                SELECT * FROM ({union_sql}) t {where_clause}
                ORDER BY CASE WHEN data_type = '超发暂存' THEN 0 ELSE 1 END,
                         part_number ASC, id ASC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).fetchall()

        return [{
            "id": r[0], "data_type": r[1], "part_number": r[2],
            "part_name": r[3], "quantity": r[4], "location": r[5], "source": r[6],
        } for r in rows], total


def delete_inventory_items(item_ids):
    with get_db() as db:
        inv_ids, ex_ids = [], []
        for i in item_ids:
            s = str(i)
            if s.startswith("ex_"):
                try:
                    ex_ids.append(int(s.replace("ex_", "")))
                except ValueError:
                    pass
            else:
                try:
                    inv_ids.append(int(s))
                except ValueError:
                    pass

        if inv_ids:
            db.query(Inventory).filter(Inventory.id.in_(inv_ids)).delete(
                synchronize_session=False
            )
        if ex_ids:
            db.query(ExcessRecord).filter(ExcessRecord.id.in_(ex_ids)).delete(
                synchronize_session=False
            )
        db.commit()


def get_parts(page, size, keyword=""):
    with get_db() as db:
        q = db.query(Part)
        if keyword:
            q = q.filter(Part.part_number.contains(keyword))
        return q.offset((page - 1) * size).limit(size).all(), q.count()


def add_part(pn, name, desc, pitch=""):
    with get_db() as db:
        db.add(Part(part_number=pn, part_name=name, description=desc, pitch=pitch))
        db.commit()


def calculate_loss(wo_number):
    with get_db() as db:
        sql = text("""
            SELECT s.part_number, p.part_name, CEIL(s.qty_per_board * w.plan_qty),
                   COALESCE((SELECT SUM(issue_qty) FROM issue_detail d
                             JOIN issue_header h ON d.issue_no = h.issue_no
                             WHERE h.wo_number = w.wo_number AND d.part_number = s.part_number), 0),
                   COALESCE((SELECT SUM(return_qty) FROM return_detail d
                             JOIN return_header h ON d.return_no = h.return_no
                             WHERE h.wo_number = w.wo_number AND d.part_number = s.part_number), 0)
            FROM wo_bom_snapshot s
            JOIN wo w ON s.wo_number = w.wo_number
            LEFT JOIN part p ON s.part_number = p.part_number
            WHERE w.wo_number = :wo
        """)
        rows = db.execute(sql, {"wo": wo_number}).fetchall()
        return [{
            "物料料号": r[0], "物料名称": r[1] or "",
            "需求数量": r[2], "领料数量": r[3], "退料数量": r[4],
            "损耗数量": r[3] - r[2] - r[4],
        } for r in rows]


def get_issue_details(issue_no):
    with get_db() as db:
        sql = text("""
            SELECT d.part_number, p.part_name, d.issue_qty, d.wo_number
            FROM issue_detail d
            LEFT JOIN part p ON d.part_number = p.part_number
            WHERE d.issue_no = :no
        """)
        rows = db.execute(sql, {"no": issue_no}).fetchall()
        return [{
            "序号": i + 1, "物料料号": r[0], "物料名称": r[1] or "",
            "数量": r[2], "所属工单": r[3],
        } for i, r in enumerate(rows)]


def get_return_details(return_no):
    with get_db() as db:
        sql = text("""
            SELECT d.part_number, p.part_name, d.return_qty, d.wo_number
            FROM return_detail d
            LEFT JOIN part p ON d.part_number = p.part_number
            WHERE d.return_no = :no
        """)
        rows = db.execute(sql, {"no": return_no}).fetchall()
        return [{
            "序号": i + 1, "物料料号": r[0], "物料名称": r[1] or "",
            "数量": r[2], "所属工单": r[3],
        } for i, r in enumerate(rows)]


def get_excess_records(keyword=""):
    with get_db() as db:
        q = db.query(ExcessRecord)
        if keyword:
            q = q.filter(ExcessRecord.part_number.contains(keyword))
        return q.all()


def sync_all_excess_records():
    """全量重算所有生产中工单的超发数据。"""
    with get_db() as db:
        db.query(ExcessRecord).delete()

        sql = text("""
            SELECT w.wo_number, w.product_name, w.line, s.part_number, p.part_name,
                   (COALESCE((SELECT SUM(issue_qty) FROM issue_detail d
                              JOIN issue_header h ON d.issue_no = h.issue_no
                              WHERE h.wo_number = w.wo_number AND d.part_number = s.part_number), 0)
                   - COALESCE((SELECT SUM(return_qty) FROM return_detail d
                               JOIN return_header h ON d.return_no = h.return_no
                               WHERE h.wo_number = w.wo_number AND d.part_number = s.part_number), 0)
                   - CEIL(s.qty_per_board * w.plan_qty)) AS excess_qty
            FROM wo_bom_snapshot s
            JOIN wo w ON s.wo_number = w.wo_number
            LEFT JOIN PART p ON s.part_number = p.part_number
            WHERE w.status = '生产中'
        """)
        results = db.execute(sql).fetchall()

        for r in results:
            wo_no, prod_name, line, part_no, part_name, excess = r
            if excess and excess > 0:
                db.add(ExcessRecord(
                    wo_number=wo_no, product_name=prod_name,
                    part_number=part_no, part_name=part_name,
                    quantity=excess, line=line,
                ))
        db.commit()
