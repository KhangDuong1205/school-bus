"""
Seed script to populate the database with vehicle types and vehicles
Run this once to create sample data
Format: {TYPE_CODE}{CAPACITY}-{NUMBER} e.g., MB20-01, SB30-02
"""
import random
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import VehicleType, Vehicle

# Sample driver names
DRIVER_NAMES = [
    "Ahmad Bin Hassan", "Lim Wei Ming", "Muthu Rajan", "Tan Ah Kow", "Wong Chee Keong",
    "Suresh Kumar", "Lee Boon Huat", "Ong Kian Beng", "Rajesh Sharma", "Chen Wei Long",
    "Mohd Faisal", "Teo Eng Chuan", "Gopal Krishnan", "Ng Beng Hock", "Abdul Rahman",
    "Siti Aminah", "Lim Poh Lin", "Kavitha Devi", "Tan Mei Ling", "Wong Su Mei",
    "Mohammad Rizal", "Tan Keng Huat", "Ravi Shankar", "Lee Ah Seng", "Ong Ah Lian",
    "Kamal Nizam", "Chong Meng Fei", "Anand Kumar", "Liew Chee Seng", "Fatimah Binte Ali"
]

def generate_plate():
    """Generate a realistic Singapore vehicle plate number"""
    prefix = random.choice(['SBS', 'SG', 'PA', 'PC', 'SMB'])
    number = random.randint(1000, 9999)
    suffix = random.choice('ABCDEFGHJKLMNPRSTUVWXYZ')
    return f"{prefix}{number}{suffix}"

def seed_database():
    with app.app_context():
        # Clear existing data
        print("Clearing existing vehicles...")
        Vehicle.query.delete()
        VehicleType.query.delete()
        db.session.commit()
        
        # Create vehicle types with codes
        print("Creating vehicle types...")
        types = [
            VehicleType(name="11-Seater Van", code="VN", routing_profile="van", capacity=11, label="🚐"),
            VehicleType(name="20-Seater Minibus", code="MB", routing_profile="van", capacity=20, label="🚌"),
            VehicleType(name="30-Seater Bus", code="SB", routing_profile="bus", capacity=30, label="🚍"),
            VehicleType(name="45-Seater Coach", code="CH", routing_profile="bus", capacity=45, label="🚎"),
        ]
        for vt in types:
            db.session.add(vt)
        db.session.commit()
        
        print(f"Created {len(types)} vehicle types")
        
        # Distribution: how many vehicles of each type
        # VN: 5, MB: 8, SB: 10, CH: 7 = 30 total
        distribution = {
            "VN": 5,   # 11-Seater Van
            "MB": 8,   # 20-Seater Minibus
            "SB": 10,  # 30-Seater Bus
            "CH": 7    # 45-Seater Coach
        }
        
        # Create vehicles
        print("Creating 30 vehicles...")
        used_plates = set()
        vehicles_created = 0
        driver_idx = 0
        
        for vtype in VehicleType.query.all():
            count = distribution.get(vtype.code, 5)
            
            for i in range(1, count + 1):
                # Generate unique plate
                plate = generate_plate()
                while plate in used_plates:
                    plate = generate_plate()
                used_plates.add(plate)
                
                # Generate ID: {CODE}{CAPACITY}-{NUMBER}
                unique_id = f"{vtype.code}{vtype.capacity}-{i:02d}"
                
                # Random status (90% active, 10% maintenance)
                status = 'active' if random.random() < 0.9 else 'maintenance'
                
                vehicle = Vehicle(
                    id=unique_id,
                    plate_number=plate,
                    nickname=f"{vtype.name} #{i}",
                    driver_name=DRIVER_NAMES[driver_idx % len(DRIVER_NAMES)],
                    status=status,
                    type_id=vtype.id
                )
                db.session.add(vehicle)
                vehicles_created += 1
                driver_idx += 1
        
        db.session.commit()
        print(f"Created {vehicles_created} vehicles")
        
        # Summary
        print("\n=== Database Summary ===")
        for vt in VehicleType.query.all():
            vehicles = Vehicle.query.filter_by(type_id=vt.id).all()
            ids = [v.id for v in vehicles]
            print(f"  {vt.code} - {vt.name}: {len(ids)} vehicles")
            print(f"      IDs: {', '.join(ids)}")
        
        active = Vehicle.query.filter_by(status='active').count()
        maintenance = Vehicle.query.filter_by(status='maintenance').count()
        print(f"\n  Active: {active}, Maintenance: {maintenance}")
        print("Done!")

if __name__ == '__main__':
    seed_database()
