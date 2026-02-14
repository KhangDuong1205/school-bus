from app import app, db
from models import Vehicle, VehicleType
import sqlalchemy as sa
from sqlalchemy.sql import text

def run_migration():
    print("Starting migration: Adding 'capacity' to 'Vehicle' table...")
    
    with app.app_context():
        # 1. Add column if it doesn't exist
        # SQLite doesn't support IF NOT EXISTS in ALTER TABLE ADD COLUMN universally,
        # so we check inspector or just try/except.
        engine = db.engine
        inspector = sa.inspect(engine)
        columns = [c['name'] for c in inspector.get_columns('vehicle')]
        
        if 'capacity' not in columns:
            print("Adding 'capacity' column...")
            try:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE vehicle ADD COLUMN capacity INTEGER"))
                    conn.commit()
                print("Column added successfully.")
            except Exception as e:
                print(f"Error adding column: {e}")
                return
        else:
            print("'capacity' column already exists.")
            
        # 2. Backfill data
        print("Backfilling capacity data from VehicleType...")
        vehicles = Vehicle.query.all()
        count = 0
        for v in vehicles:
            if v.vehicle_type and (v.capacity is None):
                v.capacity = v.vehicle_type.capacity
                count += 1
            elif v.capacity is None:
                 # Fallback if no type specific
                 v.capacity = 40
                 count += 1
        
        try:
            db.session.commit()
            print(f"Successfully updated {count} vehicles with capacity data.")
        except Exception as e:
            db.session.rollback()
            print(f"Error updating records: {e}")

if __name__ == "__main__":
    run_migration()
