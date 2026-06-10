from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String
)
from sqlalchemy.pool import StaticPool

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL

# =========================================
# DATABASE ENGINE
# =========================================

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
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

    expiry = Column(String)  # Add expiry column to distinguish between different expirations

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
# MIGRATE EXISTING DATA
# =========================================

def migrate_existing_data():
    """Add expiry column and populate with TRACK_EXPIRY if not already done"""
    
    try:
        from app.config import TRACK_EXPIRY
        import sqlite3
        
        db_path = 'oi_2026_06_03.db'
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        try:
            # Check if expiry column already exists
            cursor.execute('PRAGMA table_info(oi_snapshots)')
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if 'expiry' not in column_names:
                print("[MIGRATION] Adding 'expiry' column...")
                cursor.execute(f'ALTER TABLE oi_snapshots ADD COLUMN expiry TEXT')
                conn.commit()
                print("[MIGRATION] ✓ Column added")
            
            # Update all existing records with TRACK_EXPIRY
            cursor.execute(f'UPDATE oi_snapshots SET expiry = ? WHERE expiry IS NULL', (TRACK_EXPIRY,))
            updated_count = cursor.rowcount
            conn.commit()
            
            if updated_count > 0:
                print(f"[MIGRATION] ✓ Updated {updated_count} records with expiry {TRACK_EXPIRY}")
            
            # Verify
            cursor.execute('SELECT COUNT(*) FROM oi_snapshots WHERE expiry = ?', (TRACK_EXPIRY,))
            total = cursor.fetchone()[0]
            print(f"[MIGRATION] ✓ Total records with expiry {TRACK_EXPIRY}: {total}")
            
        except Exception as e:
            print(f"[MIGRATION] ERROR: {e}")
            conn.rollback()
        finally:
            conn.close()
            
    except Exception as e:
        print(f"[MIGRATION] Skipping migration: {e}")

# =========================================
# SAVE SNAPSHOT
# =========================================

def save_snapshot(data):

    db = SessionLocal()

    try:

        # Avoid inserting duplicate snapshots for the same timestamp/expiry/strike.
        # If a snapshot with the exact timestamp, expiry and strike exists,
        # update it instead of inserting a new row. This prevents small
        # outlier rows (same timestamp) from creating conflicting data
        # that later breaks bucket aggregation.

        existing = db.query(OISnapshot).filter_by(
            timestamp=data.get("timestamp"),
            expiry=data.get("expiry"),
            strike=data.get("strike")
        ).first()

        if existing:
            for key, val in data.items():
                setattr(existing, key, val)
            db.commit()
            return

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

def get_active_expiry(db):
    latest = (
        db.query(OISnapshot.expiry)
        .filter(OISnapshot.expiry.isnot(None))
        .order_by(OISnapshot.timestamp.desc())
        .first()
    )
    return latest[0] if latest else None