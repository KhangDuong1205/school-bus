from app import app, db
import os

print(f"Current working directory: {os.getcwd()}")
print(f"Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")

try:
    with app.app_context():
        print("Creating all tables...")
        db.create_all()
        print("Done.")
except Exception as e:
    print(f"Error creating database: {e}")

if os.path.exists('school_bus.db'):
    print("school_bus.db exists!")
else:
    print("school_bus.db DOES NOT exist!")
