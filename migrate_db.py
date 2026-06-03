import sqlite3
from app.config import TRACK_EXPIRY

def migrate_database():
    """Add expiry column to existing database and populate with TRACK_EXPIRY"""
    
    db_path = 'oi_2026_06_03.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if expiry column already exists
        cursor.execute('PRAGMA table_info(oi_snapshots)')
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'expiry' not in column_names:
            print("Adding 'expiry' column...")
            cursor.execute(f'ALTER TABLE oi_snapshots ADD COLUMN expiry TEXT')
            conn.commit()
            print("✓ Column added")
        else:
            print("✓ 'expiry' column already exists")
        
        # Update all existing records with TRACK_EXPIRY
        print(f"\nUpdating existing records with expiry: {TRACK_EXPIRY}...")
        cursor.execute(
            f'UPDATE oi_snapshots SET expiry = ? WHERE expiry IS NULL',
            (TRACK_EXPIRY,)
        )
        updated_count = cursor.rowcount
        conn.commit()
        print(f"✓ Updated {updated_count} records")
        
        # Verify
        cursor.execute('SELECT COUNT(*) FROM oi_snapshots WHERE expiry = ?', (TRACK_EXPIRY,))
        total = cursor.fetchone()[0]
        print(f"\n✓ Total records with expiry {TRACK_EXPIRY}: {total}")
        
        print("\nMigration complete! Database is ready.")
        
    except Exception as e:
        print(f"ERROR: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
