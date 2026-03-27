"""
Seed script: Delete all existing vehicles/vehicle types and add 150 buses.
- 50 x 12-seater
- 50 x 29-seater
- 50 x 49-seater
Each with a made-up plate number and driver name.
"""
import random
from app import app
from models import db, VehicleType, Vehicle

# Driver names pool
FIRST_NAMES = [
    "James", "John", "Robert", "Michael", "David", "Richard", "Joseph", "Thomas",
    "Charles", "Daniel", "Matthew", "Anthony", "Mark", "Steven", "Paul", "Andrew",
    "Kevin", "Brian", "George", "Edward", "Ronald", "Timothy", "Jason", "Jeffrey",
    "Ryan", "Jacob", "Gary", "Nicholas", "Eric", "Jonathan", "Stephen", "Larry",
    "Justin", "Scott", "Brandon", "Benjamin", "Samuel", "Raymond", "Gregory", "Frank",
    "Patrick", "Peter", "Harold", "Douglas", "Henry", "Dennis", "Jerry", "Tyler",
    "Aaron", "Nathan", "Arthur", "Philip", "Eugene", "Russell", "Bobby", "Howard",
    "Carl", "Albert", "Willie", "Ralph", "Lawrence", "Wayne", "Roy", "Jesse",
    "Vincent", "Dylan", "Alan", "Bruce", "Gabriel", "Oscar", "Louis", "Clarence",
    "Keith", "Norman", "Gerald", "Roger", "Johnny", "Martin", "Craig", "Melvin",
    "Leonard", "Stanley", "Ernest", "Victor", "Francis", "Todd", "Warren", "Eddie",
    "Darren", "Liam", "Noah", "Oliver", "Ethan", "Lucas", "Mason", "Logan",
    "Alexander", "Sebastian", "Caleb", "Jack", "Aiden", "Owen", "Isaiah", "Adrian",
    "Leo", "Parker", "Eli", "Landon", "Colton", "Jordan", "Cameron", "Hunter",
    "Miles", "Ian", "Connor", "Harrison", "Jaxon", "Cooper", "Dominic", "Easton",
    "Carson", "Asher", "Nolan", "Evan", "Gavin", "Brody", "Maxwell", "Axel",
    "Zachary", "Blake", "Chase", "Kayden", "Lincoln", "Emmett", "Ryder", "Sawyer",
    "Roman", "Beau", "Declan", "Brooks", "Bentley", "Tucker", "Josiah", "Wesley",
    "Weston", "Maddox", "Jameson", "Rowan", "Silas", "Felix", "Knox", "Kingston"
]

LAST_NAMES = [
    "Tan", "Lim", "Lee", "Ng", "Ong", "Wong", "Goh", "Chua", "Chan", "Koh",
    "Teo", "Ang", "Yeo", "Ho", "Low", "Tay", "Sim", "Chew", "Foo", "Yap",
    "Chong", "Cheong", "Pang", "Soh", "Toh", "Wee", "Seah", "Quek", "Phua", "Lai",
    "Heng", "Lau", "Leong", "Chin", "Chng", "Gan", "Sng", "Png", "Chia", "Loh",
    "Yeoh", "Kwek", "Han", "Tok", "Lew", "Eu", "Loo", "Nah", "Tee", "Yong",
    "Khoo", "Guo", "Ou", "Beh", "Siew", "Kor", "Tong", "Hung", "Mak", "Yew",
    "Neo", "Sun", "Wan", "Sum", "Pan", "Fong", "San", "Man", "Lok", "Yue",
    "Hui", "Sin", "Hoe", "Kee", "Boon", "Teck", "Wah", "Lin", "Seng", "Kim",
    "Soon", "Kai", "Meng", "Huat", "Chee", "Swee", "Ah", "Bok", "Keng", "Soo",
    "Poh", "Hong", "Chun", "Jun", "Wei", "Xin", "Ying", "Ming", "Yi", "Jie"
]

# Singapore-style plate number prefixes
PLATE_PREFIXES = ["SG", "SBS", "PA", "PC", "PB"]


def generate_plate(prefix_code, index):
    """Generate a unique Singapore-style plate number: e.g. SBS1234A"""
    prefix = random.choice(PLATE_PREFIXES)
    number = 1000 + index
    suffix = chr(65 + (index % 26))  # A-Z
    return f"{prefix}{number}{suffix}"


def generate_driver_name(used_names):
    """Generate a unique driver name."""
    while True:
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        if name not in used_names:
            used_names.add(name)
            return name


def seed():
    with app.app_context():
        print("=== Deleting all existing vehicles ===")
        Vehicle.query.delete()
        print("=== Deleting all existing vehicle types ===")
        VehicleType.query.delete()
        db.session.commit()
        print("Deleted all vehicle and vehicle type records.\n")

        # Create 3 vehicle types
        types_data = [
            {"name": "12-Seater Minibus", "code": "MB", "routing_profile": "van", "capacity": 12, "label": "🚐"},
            {"name": "29-Seater Bus",     "code": "SB", "routing_profile": "van", "capacity": 29, "label": "🚌"},
            {"name": "49-Seater Coach",   "code": "CB", "routing_profile": "allbus", "capacity": 49, "label": "🚍"},
        ]

        created_types = []
        for td in types_data:
            vt = VehicleType(**td)
            db.session.add(vt)
            db.session.flush()  # Get the ID
            created_types.append(vt)
            print(f"Created VehicleType: {vt.name} (id={vt.id}, capacity={vt.capacity})")

        # Create 50 vehicles for each type (150 total)
        used_names = set()
        plate_counter = 0

        for vt in created_types:
            print(f"\n--- Creating 50 vehicles for {vt.name} ---")
            for i in range(1, 51):
                plate_counter += 1
                plate = generate_plate(vt.code, plate_counter)
                driver = generate_driver_name(used_names)
                vehicle_id = f"{vt.code}{vt.capacity}-{i:02d}"
                nickname = f"{vt.name.split()[0]}-Seat #{i}"

                v = Vehicle(
                    id=vehicle_id,
                    plate_number=plate,
                    nickname=nickname,
                    driver_name=driver,
                    status="active",
                    capacity=vt.capacity,
                    type_id=vt.id,
                )
                db.session.add(v)

            print(f"  Created 50 vehicles ({vt.code}{vt.capacity}-01 .. {vt.code}{vt.capacity}-50)")

        db.session.commit()
        print(f"\n=== Done! Total vehicles in DB: {Vehicle.query.count()} ===")
        print(f"  12-seater: {Vehicle.query.filter(Vehicle.id.like('MB12-%')).count()}")
        print(f"  29-seater: {Vehicle.query.filter(Vehicle.id.like('SB29-%')).count()}")
        print(f"  49-seater: {Vehicle.query.filter(Vehicle.id.like('CB49-%')).count()}")


if __name__ == "__main__":
    seed()
