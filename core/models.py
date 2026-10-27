from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import declarative_base
from core.database import engine

Base = declarative_base()


class Part(Base):
    __tablename__ = 'part'
    id = Column(Integer, primary_key=True)
    part_number = Column(String, unique=True, index=True)
    part_name = Column(String)
    description = Column(String)
    pitch = Column(String)


class BOM_Header(Base):
    __tablename__ = 'bom_header'
    id = Column(Integer, primary_key=True)
    product_number = Column(String, index=True)
    product_name = Column(String)
    version = Column(String)


class BOM_Detail(Base):
    __tablename__ = 'bom_detail'
    id = Column(Integer, primary_key=True)
    bom_id = Column(Integer, index=True)
    part_number = Column(String, index=True)
    qty_per_board = Column(Float)


class WorkOrder(Base):
    __tablename__ = 'wo'
    id = Column(Integer, primary_key=True)
    wo_number = Column(String, unique=True, index=True)
    line = Column(String)
    product_number = Column(String, index=True)
    product_name = Column(String)
    plan_qty = Column(Integer)
    produce_date = Column(String)
    status = Column(String, default='待生产')
    bom_version = Column(String)


class WOBomSnapshot(Base):
    __tablename__ = 'wo_bom_snapshot'
    id = Column(Integer, primary_key=True)
    wo_number = Column(String, index=True)
    part_number = Column(String, index=True)
    qty_per_board = Column(Float)


class Inventory(Base):
    __tablename__ = 'inventory'
    id = Column(Integer, primary_key=True)
    part_number = Column(String, index=True)
    part_name = Column(String)
    quantity = Column(Integer)
    location = Column(String)
    source = Column(String, default='手动导入')


class IssueHeader(Base):
    __tablename__ = 'issue_header'
    id = Column(Integer, primary_key=True)
    issue_no = Column(String, unique=True, index=True)
    wo_number = Column(String, index=True)
    operator = Column(String)
    total_qty = Column(Integer)


class IssueDetail(Base):
    __tablename__ = 'issue_detail'
    id = Column(Integer, primary_key=True)
    issue_no = Column(String, index=True)
    wo_number = Column(String, index=True)   # 优化：加索引，超发同步 SQL 频繁按此过滤
    part_number = Column(String, index=True)
    issue_qty = Column(Integer)


class ReturnHeader(Base):
    __tablename__ = 'return_header'
    id = Column(Integer, primary_key=True)
    return_no = Column(String, unique=True, index=True)
    wo_number = Column(String, index=True)
    operator = Column(String)
    total_qty = Column(Integer)


class ReturnDetail(Base):
    __tablename__ = 'return_detail'
    id = Column(Integer, primary_key=True)
    return_no = Column(String, index=True)
    wo_number = Column(String, index=True)
    part_number = Column(String, index=True)
    return_qty = Column(Integer)


class FinishHeader(Base):
    __tablename__ = 'finish_header'
    id = Column(Integer, primary_key=True)
    finish_no = Column(String, unique=True, index=True)
    wo_number = Column(String, index=True)
    product_number = Column(String)
    product_name = Column(String)
    total_qty = Column(Integer)
    operator = Column(String)


class ExcessRecord(Base):
    __tablename__ = 'excess_record'
    id = Column(Integer, primary_key=True)
    wo_number = Column(String, index=True)
    product_name = Column(String)
    part_number = Column(String, index=True)  # 优化：加索引
    part_name = Column(String)
    quantity = Column(Integer)
    line = Column(String)


Base.metadata.create_all(engine)
