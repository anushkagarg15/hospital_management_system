import sqlite3
import hashlib
from datetime import datetime

DB_NAME = 'hms.db'
DEFAULT_ADMIN_USERNAME = 'admin'
DEFAULT_ADMIN_PASSWORD = 'admin_password_123'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row 
    conn.execute('PRAGMA foreign_keys = ON;') 
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS User (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Admin', 'Doctor', 'Patient'))
        );
    ''')


    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Specialization (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT
        );
    ''')
    

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Doctor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            name TEXT NOT NULL,
            specialization_id INTEGER NOT NULL,
            contact_info TEXT,
            is_blacklisted BOOLEAN NOT NULL DEFAULT 0,  
            FOREIGN KEY (user_id) REFERENCES User(id),
            FOREIGN KEY (specialization_id) REFERENCES Specialization(id)
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Patient (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            name TEXT NOT NULL,
            contact_info TEXT UNIQUE NOT NULL,
            is_blacklisted BOOLEAN NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES User(id)
        );
    ''')


    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Appointment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            date DATE NOT NULL,
            time TIME NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Booked', 'Completed', 'Cancelled')),
            FOREIGN KEY (patient_id) REFERENCES Patient(id),
            FOREIGN KEY (doctor_id) REFERENCES Doctor(id),
            UNIQUE (doctor_id, date, time) 
        );
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Treatment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id INTEGER UNIQUE NOT NULL,
            diagnosis TEXT NOT NULL,
            prescription TEXT,
            doctor_notes TEXT,
            treatment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (appointment_id) REFERENCES Appointment(id)
        );
    ''')
    
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS DoctorAvailability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id INTEGER NOT NULL,
            date DATE NOT NULL,
            start_time TIME NOT NULL,
            is_booked BOOLEAN NOT NULL DEFAULT 0,
            FOREIGN KEY (doctor_id) REFERENCES Doctor(id),
            UNIQUE (doctor_id, date, start_time) 
        );
    ''')

    conn.commit()


    conn.commit()
    conn.close()
    print("Database tables created successfully.")

def seed_initial_data():
    """Inserts the pre-existing Admin and initial Specializations."""
    conn = get_db_connection()
    cursor = conn.cursor()
    

    password_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
    
    try:
        cursor.execute("INSERT INTO User (username, password_hash, role) VALUES (?, ?, ?)", 
                       (DEFAULT_ADMIN_USERNAME, password_hash, 'Admin'))
        print(f"Admin user '{DEFAULT_ADMIN_USERNAME}' created with password '{DEFAULT_ADMIN_PASSWORD}'.")
    except sqlite3.IntegrityError:
        print("Admin user already exists. Skipping insertion.")


    specializations = [
        ('Cardiology', 'Heart and blood vessel disorders.'),
        ('Pediatrics', 'Medical care of infants, children, and adolescents.'),
        ('Neurology', 'Disorders of the nervous system.')
    ]

    for name, desc in specializations:
        cursor.execute("INSERT OR IGNORE INTO Specialization (name, description) VALUES (?, ?)", (name, desc))

    conn.commit()
    conn.close()
    print("Initial data (Admin, Specializations) seeded successfully.")

if __name__ == '__main__':
    create_tables()
    seed_initial_data()