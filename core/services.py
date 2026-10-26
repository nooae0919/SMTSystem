from core.database import SessionLocal
from core.models import *
from sqlalchemy import text, func
from datetime import datetime

# ==================== 1. 工单管理 ====================
def get_wos(page, size):
    db = SessionLocal()
    try:
        q = db.query(
            WorkOrder,
            func.coalesce(func.sum(FinishHeader.total_qty), 0).label('finished_qty')
        ).outerjoin(FinishHeader, WorkOrder.wo_number == FinishHeader.wo_number)\
         .group_by(WorkOrder.id).order_by(WorkOrder.id.desc())
         
        total = q.count()
        records = q.offset((page-1)*size).limit(size).all()
        return records, total
    finally: db.close()

def create_wo_with_snapshot(wo_no, line, prod_no, prod_name, qty, produce_date, bom_id, status='待生产'):
    db = SessionLocal()
    try:
        # 1. 直接通过 ID 获取 BOM 主表
        bom_head = db.query(BOM_Header).filter_by(id=bom_id).first()
        if not bom_head: raise ValueError("找不到该 BOM 数据")
        
        # 2. 创建工单，自动带上成品料号和名称
        db.add(WorkOrder(
            wo_number=wo_no, 
            line=line, 
            product_number=prod_no, 
            product_name=prod_name, 
            plan_qty=qty, 
            produce_date=produce_date, 
            status=status, 
            bom_version=bom_head.version
        ))
        
        # 3. 写入 BOM 快照
        bom_details = db.query(BOM_Detail).filter_by(bom_id=bom_id).all()
        for d in bom_details:
            db.add(WOBomSnapshot(wo_number=wo_no, part_number=d.part_number, qty_per_board=d.qty_per_board))
        
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally: db.close()

def update_wo(wo_number, line, qty, produce_date, status):
    db = SessionLocal()
    try:
        wo = db.query(WorkOrder).filter_by(wo_number=wo_number).first()
        if wo:
            wo.line = line
            wo.plan_qty = qty
            wo.produce_date = produce_date
            wo.status = status
            db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally: db.close()

def delete_wos(wo_numbers):
    db = SessionLocal()
    try:
        db.query(WorkOrder).filter(WorkOrder.wo_number.in_(wo_numbers)).delete(synchronize_session=False)
        db.query(WOBomSnapshot).filter(WOBomSnapshot.wo_number.in_(wo_numbers)).delete(synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally: db.close()

# ==================== 2. BOM 管理 ====================
def get_bom_headers(page, size):
    db = SessionLocal()
    try:
        q = db.query(BOM_Header).order_by(BOM_Header.id.desc())
        return q.offset((page-1)*size).limit(size).all(), q.count()
    finally: db.close()

def get_bom_details(bom_id):
    db = SessionLocal()
    try:
        # 直接通过 ORM 查询明细表，避免复杂的 SQL 关联出错
        details = db.query(BOM_Detail).filter_by(bom_id=bom_id).all()
        
        result = []
        for d in details:
            # 根据料号去 Part 表里查出名称
            part = db.query(Part).filter_by(part_number=d.part_number).first()
            part_name = part.part_name if part else ''
            
            result.append({
                '子件料号': d.part_number,
                '子件名称': part_name,
                '基础用量': d.qty_per_board
            })
        return result
    finally:
        db.close()

def delete_boms(bom_ids):
    db = SessionLocal()
    try:
        db.query(BOM_Detail).filter(BOM_Detail.bom_id.in_(bom_ids)).delete(synchronize_session=False)
        db.query(BOM_Header).filter(BOM_Header.id.in_(bom_ids)).delete(synchronize_session=False)
        db.commit()
    finally: db.close()

def create_bom_with_details(prod_no, prod_name, version, items):
    db = SessionLocal()
    try:
        bom_head = BOM_Header(product_number=prod_no, product_name=prod_name, version=version)
        db.add(bom_head)
        db.flush() 
        for item in items:
            db.add(BOM_Detail(bom_id=bom_head.id, part_number=item['part_number'], qty_per_board=item['qty_per_board']))
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally: db.close()

# ==================== 3. 领料/退料 (包含删除功能) ====================
def submit_issue(operator, items):
    db = SessionLocal()
    try:
        issue_no = f"IS{datetime.now().strftime('%m%d%H%M%S')}"
        total_qty = sum(i['issue_qty'] for i in items)
        first_wo = items[0]['wo_number'] if items else ""
        db.add(IssueHeader(issue_no=issue_no, wo_number=first_wo, operator=operator, total_qty=total_qty))
        
        touched_wos = set()
        for item in items:
            wo_num = item['wo_number']
            touched_wos.add(wo_num)
            db.execute(
                text("INSERT INTO issue_detail (issue_no, part_number, issue_qty, wo_number) VALUES (:no, :pn, :qty, :wo)"),
                {"no": issue_no, "pn": item['part_number'], "qty": item['issue_qty'], "wo": wo_num}
            )
        for wo in touched_wos:
            wo_obj = db.query(WorkOrder).filter_by(wo_number=wo).first()
            if wo_obj and wo_obj.status == '待生产':
                wo_obj.status = '生产中'
        db.commit()
        return issue_no
    except Exception as e:
        db.rollback()
        raise e
    finally: db.close()

def delete_issues(issue_nos):
    db = SessionLocal()
    try:
        db.query(IssueHeader).filter(IssueHeader.issue_no.in_(issue_nos)).delete(synchronize_session=False)
        db.query(IssueDetail).filter(IssueDetail.issue_no.in_(issue_nos)).delete(synchronize_session=False)
        db.commit()
    finally: db.close()

def submit_return(operator, items):
    db = SessionLocal()
    try:
        return_no = f"RT{datetime.now().strftime('%m%d%H%M%S')}"
        total_qty = sum(i['return_qty'] for i in items)
        first_wo = items[0]['wo_number'] if items else ""
        db.add(ReturnHeader(return_no=return_no, wo_number=first_wo, operator=operator, total_qty=total_qty))
        
        for item in items:
            db.execute(
                text("INSERT INTO return_detail (return_no, part_number, return_qty, wo_number) VALUES (:no, :pn, :qty, :wo)"),
                {"no": return_no, "pn": item['part_number'], "qty": item['return_qty'], "wo": item['wo_number']}
            )
        db.commit()
        return return_no
    except Exception as e:
        db.rollback()
        raise e
    finally: db.close()

def delete_returns(return_nos):
    db = SessionLocal()
    try:
        db.query(ReturnHeader).filter(ReturnHeader.return_no.in_(return_nos)).delete(synchronize_session=False)
        db.query(ReturnDetail).filter(ReturnDetail.return_no.in_(return_nos)).delete(synchronize_session=False)
        db.commit()
    finally: db.close()

def submit_finish(wo_number, prod_no, prod_name, finish_qty, operator):
    db = SessionLocal()
    try:
        finish_no = f"FG{datetime.now().strftime('%m%d%H%M%S')}"
        db.add(FinishHeader(finish_no=finish_no, wo_number=wo_number, product_number=prod_no, product_name=prod_name, total_qty=finish_qty, operator=operator))
        
        wo = db.query(WorkOrder).filter_by(wo_number=wo_number).first()
        if wo:
            total_finished = db.query(func.sum(FinishHeader.total_qty)).filter_by(wo_number=wo_number).scalar() or 0
            if total_finished >= wo.plan_qty:
                wo.status = '已完成'
        db.commit()
        return finish_no
    except Exception as e:
        db.rollback()
        raise e
    finally: db.close()

def delete_finishes(finish_nos):
    db = SessionLocal()
    try:
        db.query(FinishHeader).filter(FinishHeader.finish_no.in_(finish_nos)).delete(synchronize_session=False)
        db.commit()
    finally: db.close()

# ==================== 4. 查询与统计算法 ====================
def get_issue_list(page, size):
    db = SessionLocal()
    try:
        q = db.query(IssueHeader).order_by(IssueHeader.id.desc())
        return q.offset((page-1)*size).limit(size).all(), q.count()
    finally: db.close()

def get_return_list(page, size):
    db = SessionLocal()
    try:
        q = db.query(ReturnHeader).order_by(ReturnHeader.id.desc())
        return q.offset((page-1)*size).limit(size).all(), q.count()
    finally: db.close()

def get_finish_list(page, size):
    db = SessionLocal()
    try:
        q = db.query(FinishHeader).order_by(FinishHeader.id.desc())
        return q.offset((page-1)*size).limit(size).all(), q.count()
    finally: db.close()

def get_unfinished_wos():
    db = SessionLocal()
    try:
        return db.query(WorkOrder).filter(WorkOrder.status != '已完成').all()
    finally: db.close()

def auto_fill_excess_inventory():
    db = SessionLocal()
    try:
        db.query(Inventory).filter_by(source='超发入库').delete()
        sql = text("""
            SELECT w.line as location, s.part_number, p.part_name,
                   (COALESCE((SELECT SUM(issue_qty) FROM issue_detail d JOIN issue_header h ON d.issue_no = h.issue_no WHERE h.wo_number = w.wo_number AND d.part_number = s.part_number), 0) 
                   - CEIL(s.qty_per_board * w.plan_qty)) as excess_qty
            FROM wo_bom_snapshot s
            JOIN wo w ON s.wo_number = w.wo_number
            LEFT JOIN part p ON s.part_number = p.part_number
            WHERE w.status = '生产中'
        """)
        results = db.execute(sql).fetchall()
        for row in results:
            location, part_number, part_name, excess = row
            if excess and excess > 0:
                db.add(Inventory(part_number=part_number, part_name=part_name, quantity=excess, location=location, source='超发入库'))
        db.commit()
    finally: db.close()

def get_inventory(page, size, keyword="", search_type="料号"):
    db = SessionLocal()
    try:
        q = db.query(Inventory)
        if keyword:
            if search_type == '料号': q = q.filter(Inventory.part_number.contains(keyword))
            else: q = q.filter(Inventory.location.contains(keyword))
        return q.offset((page-1)*size).limit(size).all(), q.count()
    finally: db.close()

def get_parts(page, size, keyword=""):
    db = SessionLocal()
    try:
        q = db.query(Part)
        if keyword: q = q.filter(Part.part_number.contains(keyword))
        return q.offset((page-1)*size).limit(size).all(), q.count()
    finally: db.close()

def add_part(pn, name, desc, pitch=""):
    db = SessionLocal()
    try:
        db.add(Part(part_number=pn, part_name=name, description=desc, pitch=pitch))
        db.commit()
    finally: db.close()

def calculate_loss(wo_number):
    db = SessionLocal()
    try:
        sql = text("""
            SELECT s.part_number, CEIL(s.qty_per_board * w.plan_qty),
                   COALESCE((SELECT SUM(issue_qty) FROM issue_detail d JOIN issue_header h ON d.issue_no = h.issue_no WHERE h.wo_number = w.wo_number AND d.part_number = s.part_number), 0),
                   COALESCE((SELECT SUM(return_qty) FROM return_detail d JOIN return_header h ON d.return_no = h.return_no WHERE h.wo_number = w.wo_number AND d.part_number = s.part_number), 0)
            FROM wo_bom_snapshot s JOIN wo w ON s.wo_number = w.wo_number WHERE w.wo_number = :wo
        """)
        rows = db.execute(sql, {"wo": wo_number}).fetchall()
        return [{'物料料号': r[0], '需求数量': r[1], '领料数量': r[2], '退料数量': r[3], '损耗数量': r[2]-r[1]-r[3]} for r in rows]
    finally: db.close()

def get_bom_export_details(bom_ids):
    db = SessionLocal()
    try:
        if not bom_ids:
            return []
        sql = text("""
            SELECT h.product_number, h.product_name, h.version, 
                   d.part_number, p.part_name, d.qty_per_board
            FROM bom_header h
            JOIN bom_detail d ON h.id = d.bom_id
            LEFT JOIN part p ON d.part_number = p.part_number
            WHERE h.id IN :ids
        """)
        result = db.execute(sql, {"ids": tuple(bom_ids)}).fetchall()
        return [{
            '成品料号': r[0], '成品名称': r[1], '版本号': r[2],
            '子件料号': r[3], '子件名称': r[4] or '', '基础用量': r[5]
        } for r in result]
    finally:
        db.close()

def delete_inventory_items(item_ids):
    db = SessionLocal()
    try:
        db.query(Inventory).filter(Inventory.id.in_(item_ids)).delete(synchronize_session=False)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

def get_issue_details(issue_no):
    db = SessionLocal()
    try:
        details = db.query(IssueDetail).filter_by(issue_no=issue_no).all()
        return [{'物料料号': d.part_number, '数量': d.issue_qty, '所属工单': d.wo_number} for d in details]
    finally: db.close()

def get_return_details(return_no):
    db = SessionLocal()
    try:
        details = db.query(ReturnDetail).filter_by(return_no=return_no).all()
        return [{'物料料号': d.part_number, '数量': d.return_qty, '所属工单': d.wo_number} for d in details]
    finally: db.close()
