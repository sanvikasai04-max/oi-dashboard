from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String
)

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL

# =========================================
# DATABASE ENGINE
# =========================================

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

# =========================================
# TABLE MODEL
# =========================================

class OISnapshot(Base):

    __tablename__ = "oi_snapshots"

    id = Column(Integer, primary_key=True, index=True)

    timestamp = Column(String)

    strike = Column(Float)

    spot = Column(Float)

    # =====================================
    # OI
    # =====================================

    call_oi = Column(Integer)

    put_oi = Column(Integer)

    # =====================================
    # PRICE
    # =====================================

    call_price = Column(Float)

    put_price = Column(Float)

    # =====================================
    # VOLUME
    # =====================================

    call_volume = Column(Integer)

    put_volume = Column(Integer)

    # =====================================
    # GREEKS
    # =====================================

    call_delta = Column(Float)

    put_delta = Column(Float)

    call_gamma = Column(Float)

    put_gamma = Column(Float)

    call_iv = Column(Float)

    put_iv = Column(Float)

# =========================================
# CREATE TABLES
# =========================================

def create_tables():

    Base.metadata.create_all(bind=engine)

# =========================================
# SAVE SNAPSHOT
# =========================================

def save_snapshot(data):

    db = SessionLocal()

    try:

        snapshot = OISnapshot(**data)

        db.add(snapshot)

        db.commit()

    except Exception as e:

        print("DB SAVE ERROR:", e)

        db.rollback()

    finally:

        db.close()

# =========================================
# FETCH SNAPSHOTS
# =========================================

def fetch_snapshots():

    db = SessionLocal()

    try:

        data = db.query(OISnapshot).all()

        return data

    finally:

        db.close()