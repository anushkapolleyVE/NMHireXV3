"""Initialize PostgreSQL Database with only the required tables.

Run this script whenever you configure a new DATABASE_URL in .env:
    python init_db.py
"""

import sys
from app.database import engine
from app.models import Base

def init_database():
    print(f"Connecting to database...")
    print(f"Tables to be created in the database:")
    for table_name in Base.metadata.tables.keys():
        print(f"  [+] {table_name}")

    try:
        Base.metadata.create_all(bind=engine)
        print("\nAll required tables created successfully in the database!")
    except Exception as e:
        print(f"\nError initializing database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    init_database()
