from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import get_db_connection, create_tables, seed_initial_data, hash_password
import sqlite3
from datetime import datetime, date, timedelta

app = Flask(__name__)
app.secret_key = 'hms_super_secret_key_845jfg' 


def is_logged_in(f):
    def wrapper(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Please log in to view this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def has_role(required_role):
    def decorator(f):
        @is_logged_in
        def wrapper(*args, **kwargs):
            if session.get('role') != required_role:
                flash(f'Access denied. Only {required_role} can access this.', 'danger')
                return redirect(url_for('dashboard')) 
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

#Routes
@app.route('/')
def index():
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        password_hash = hash_password(password)
        
        conn = get_db_connection()
        user = conn.execute("SELECT id, username, role FROM User WHERE username = ? AND password_hash = ?", 
                            (username, password_hash)).fetchone()
        conn.close()

        if user:
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        
        flash('Invalid username or password.', 'danger')
        return render_template('login.html', username=username)
    
    return render_template('login.html')

@app.route('/logout')
@is_logged_in
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@is_logged_in
def dashboard():
    role = session['role']
    user_id = session['user_id']
    
    conn = get_db_connection()
    
    if role == 'Admin':
        conn.close()
        return redirect(url_for('admin_dashboard'))
        
    elif role == 'Doctor':
        doctor = conn.execute("SELECT id FROM Doctor WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        if doctor:
            session['doctor_id'] = doctor['id']
            return redirect(url_for('doctor_dashboard'))
        flash('Doctor profile not found. Contact Admin.', 'danger')
        session.clear()
        return redirect(url_for('login'))

    elif role == 'Patient':
        patient = conn.execute("SELECT id FROM Patient WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        if patient:
            session['patient_id'] = patient['id']
            return redirect(url_for('patient_dashboard'))
        flash('Patient profile not found. Please register.', 'danger')
        session.clear()
        return redirect(url_for('login'))
            
    conn.close()
    return redirect(url_for('login')) 


#Admin routes

@app.route('/admin/dashboard')
@has_role('Admin')
def admin_dashboard():
    conn = get_db_connection()
    total_doctors = conn.execute("SELECT COUNT(*) FROM Doctor").fetchone()[0]
    total_patients = conn.execute("SELECT COUNT(*) FROM Patient").fetchone()[0]
    total_appointments = conn.execute("SELECT COUNT(*) FROM Appointment").fetchone()[0]
    conn.close()
    
    context = {
        'total_doctors': total_doctors,
        'total_patients': total_patients,
        'total_appointments': total_appointments,
        'section_title': 'Admin Dashboard'
    }
    return render_template('admin/dashboard.html', **context)


@app.route('/admin/doctors', methods=['GET', 'POST'])
@has_role('Admin')
def manage_doctors():
    conn = get_db_connection()
    
    if request.method == 'GET':
        doctors = conn.execute("""
            SELECT 
                d.id, d.name, d.contact_info, s.name AS specialization, u.username, u.id as user_id, d.is_blacklisted 
            FROM Doctor d
            JOIN Specialization s ON d.specialization_id = s.id
            JOIN User u ON d.user_id = u.id
            ORDER BY d.name
        """).fetchall()
        
        specializations = conn.execute("SELECT id, name FROM Specialization ORDER BY name").fetchall()
        conn.close()
        
        context = {
            'doctors': doctors,
            'specializations': specializations,
            'section_title': 'Manage Doctors'
        }
        return render_template('admin/manage_doctors.html', **context)

    if request.method == 'POST':
        name = request.form.get('name')
        contact_info = request.form.get('contact_info')
        specialization_id = request.form.get('specialization_id')
        username = request.form.get('username')
        password = request.form.get('password')

        if not all([name, specialization_id, username, password, contact_info]):
            flash('All fields are required to add a new doctor.', 'danger')
            conn.close()
            return redirect(url_for('manage_doctors'))

        password_hash = hash_password(password)
        cursor = conn.cursor()
        
        try:
            cursor.execute("INSERT INTO User (username, password_hash, role) VALUES (?, ?, 'Doctor')",
                           (username, password_hash))
            user_id = cursor.lastrowid
            
            cursor.execute("INSERT INTO Doctor (user_id, name, specialization_id, contact_info) VALUES (?, ?, ?, ?)",
                           (user_id, name, specialization_id, contact_info))
            
            conn.commit()
            flash(f'Doctor {name} added successfully!', 'success')
            
        except sqlite3.IntegrityError as e:
            conn.rollback()
            if 'UNIQUE constraint failed: User.username' in str(e):
                 flash('Username already exists. Doctor not added.', 'danger')
            else:
                 flash(f'Database error during doctor creation: {e}', 'danger')

        finally:
            conn.close()
            return redirect(url_for('manage_doctors'))


@app.route('/admin/doctors/toggle_blacklist/<int:doctor_id>', methods=['POST'])
@has_role('Admin')
def toggle_doctor_blacklist(doctor_id):
    conn = get_db_connection()
    
    doctor = conn.execute("SELECT name, is_blacklisted FROM Doctor WHERE id = ?", (doctor_id,)).fetchone()
    if not doctor:
        conn.close()
        flash('Doctor not found.', 'danger')
        return redirect(url_for('manage_doctors'))

    # Toggle the status
    new_status = 1 if doctor['is_blacklisted'] == 0 else 0
    action = "Blacklisted" if new_status == 1 else "Activated"
    
    conn.execute("UPDATE Doctor SET is_blacklisted = ? WHERE id = ?", (new_status, doctor_id))
    conn.commit()
    conn.close()
    
    flash(f'Doctor {doctor["name"]} has been successfully {action}.', 'info')
    return redirect(url_for('manage_doctors'))


@app.route('/admin/doctors/edit/<int:doctor_id>', methods=['GET', 'POST'])
@has_role('Admin')
def edit_doctor(doctor_id):
    conn = get_db_connection()
    
    if request.method == 'POST':
        name = request.form.get('name')
        specialization_id = request.form.get('specialization_id')
        contact_info = request.form.get('contact_info')
        
        if not all([name, specialization_id, contact_info]):
            flash('Name, specialization, and contact info are required.', 'danger')
        else:
            try:
                conn.execute("""
                    UPDATE Doctor SET name = ?, specialization_id = ?, contact_info = ?
                    WHERE id = ?
                """, (name, specialization_id, contact_info, doctor_id))
                conn.commit()
                flash(f'Doctor details updated successfully!', 'success')
            except sqlite3.IntegrityError:
                flash('An error occurred during update.', 'danger')

        conn.close()
        return redirect(url_for('manage_doctors'))

    doctor_data = conn.execute("""
        SELECT d.id, d.name, d.specialization_id, d.contact_info, u.username 
        FROM Doctor d 
        JOIN User u ON d.user_id = u.id 
        WHERE d.id = ?
    """, (doctor_id,)).fetchone()
    
    specializations = conn.execute("SELECT id, name FROM Specialization ORDER BY name").fetchall()
    conn.close()

    if not doctor_data:
        flash('Doctor not found.', 'danger')
        return redirect(url_for('manage_doctors'))
        
    context = {
        'doctor': doctor_data,
        'specializations': specializations,
        'section_title': f'Edit Doctor: {doctor_data["name"]}'
    }
    return render_template('admin/edit_doctor.html', **context)


@app.route('/admin/appointments')
@has_role('Admin')
def view_all_appointments():
    conn = get_db_connection()
    
    appointments = conn.execute("""
        SELECT 
            a.id, a.date, a.time, a.status,
            p.name AS patient_name,
            d.name AS doctor_name,
            s.name AS specialization
        FROM Appointment a
        JOIN Patient p ON a.patient_id = p.id
        JOIN Doctor d ON a.doctor_id = d.id
        JOIN Specialization s ON d.specialization_id = s.id
        ORDER BY a.date DESC, a.time DESC
    """).fetchall()
    
    conn.close()
    
    context = {
        'appointments': appointments,
        'section_title': 'All Appointments Report'
    }
    return render_template('admin/all_appointments.html', **context)


@app.route('/admin/patients')
@has_role('Admin')
def view_all_patients():
    conn = get_db_connection()
    
    patients = conn.execute("""
        SELECT id, name, contact_info FROM Patient
        ORDER BY name
    """).fetchall()
    
    conn.close()
    
    context = {
        'patients': patients,
        'section_title': 'All Registered Patients'
    }
    return render_template('admin/all_patients.html', **context)


#Doctor routes

@app.route('/doctor/dashboard')
@has_role('Doctor')
def doctor_dashboard():
    doctor_id = session.get('doctor_id')
    conn = get_db_connection()
    
    
    today = date.today()
    next_seven_days = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
    
    availability = conn.execute("""
        SELECT id, date, start_time, is_booked FROM DoctorAvailability 
        WHERE doctor_id = ? AND date BETWEEN ? AND ?
        ORDER BY date, start_time
    """, (doctor_id, next_seven_days[0], next_seven_days[-1])).fetchall()
    
    grouped_availability = {}
    for day in next_seven_days:
        grouped_availability[day] = [slot for slot in availability if slot['date'] == day]

    
    upcoming_appointments = conn.execute("""
        SELECT 
            a.id, a.date, a.time, a.status, 
            p.name AS patient_name, 
            p.id AS patient_id
        FROM Appointment a
        JOIN Patient p ON a.patient_id = p.id
        WHERE 
            a.doctor_id = ? 
            AND a.status = 'Booked'
            AND a.date >= ?
        ORDER BY a.date, a.time
    """, (doctor_id, today.strftime('%Y-%m-%d'))).fetchall()

    
    recent_completed = conn.execute("""
        SELECT 
            a.id, a.date, a.time, 
            p.name AS patient_name, 
            p.id AS patient_id,
            t.diagnosis
        FROM Appointment a
        JOIN Patient p ON a.patient_id = p.id
        JOIN Treatment t ON a.id = t.appointment_id
        WHERE 
            a.doctor_id = ? 
            AND a.status = 'Completed'
        ORDER BY a.date DESC, a.time DESC
        LIMIT 5
    """, (doctor_id,)).fetchall()
    
    conn.close()
    
    context = {
        'doctor_id': doctor_id,
        'next_seven_days': next_seven_days,
        'grouped_availability': grouped_availability,
        'upcoming_appointments': upcoming_appointments,
        'recent_completed': recent_completed,
        'section_title': 'Doctor Dashboard'
    }
    return render_template('doctor/dashboard.html', **context)


@app.route('/doctor/set_availability', methods=['POST'])
@has_role('Doctor')
def set_availability():
    doctor_id = session.get('doctor_id')
    date_str = request.form.get('date')
    time_str = request.form.get('time')
    
    if not date_str or not time_str:
        flash('Date and time are required.', 'danger')
        return redirect(url_for('doctor_dashboard'))
    
    
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        if selected_date < date.today():
            flash('Cannot add availability for a past date.', 'danger')
            return redirect(url_for('doctor_dashboard'))
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('doctor_dashboard'))

    conn = get_db_connection()
    
    try:
        existing_slot = conn.execute("""
            SELECT * FROM DoctorAvailability 
            WHERE doctor_id = ? AND date = ? AND start_time = ?
        """, (doctor_id, date_str, time_str)).fetchone()
        
        if existing_slot:
            flash(f'Slot on {date_str} at {time_str} already exists!', 'info')
        else:
            conn.execute("INSERT INTO DoctorAvailability (doctor_id, date, start_time) VALUES (?, ?, ?)",
                         (doctor_id, date_str, time_str))
            conn.commit()
            flash(f'Availability added for {date_str} at {time_str}.', 'success')
            
    except sqlite3.IntegrityError as e:
        flash(f'Database error: Slot conflicts with an existing entry: {e}', 'danger')
        conn.rollback()
        
    finally:
        conn.close()
        return redirect(url_for('doctor_dashboard'))


@app.route('/doctor/consult/<int:appointment_id>', methods=['GET'])
@has_role('Doctor')
def consultation_form(appointment_id):
    conn = get_db_connection()
    
    appointment = conn.execute("""
        SELECT a.id, a.date, a.time, a.status, p.id AS patient_id, p.name AS patient_name 
        FROM Appointment a
        JOIN Patient p ON a.patient_id = p.id
        WHERE a.id = ? AND a.doctor_id = ? AND a.status = 'Booked'
    """, (appointment_id, session.get('doctor_id'))).fetchone()
    
    if not appointment:
        flash('Appointment not found or not ready for consultation.', 'danger')
        conn.close()
        return redirect(url_for('doctor_dashboard'))

    
    history = conn.execute("""
        SELECT 
            t.treatment_date, t.diagnosis 
        FROM Treatment t
        JOIN Appointment a ON t.appointment_id = a.id
        WHERE a.patient_id = ?
        ORDER BY t.treatment_date DESC
    """, (appointment['patient_id'],)).fetchall()

    conn.close()
    
    context = {
        'appointment': appointment,
        'history': history,
        'section_title': f"Consultation: {appointment['patient_name']}"
    }
    return render_template('doctor/consultation_form.html', **context)


@app.route('/doctor/submit_treatment/<int:appointment_id>', methods=['POST'])
@has_role('Doctor')
def submit_treatment(appointment_id):
    diagnosis = request.form.get('diagnosis')
    prescription = request.form.get('prescription')
    doctor_notes = request.form.get('doctor_notes')
    
    if not diagnosis:
        flash('Diagnosis is required to submit treatment.', 'danger')
        return redirect(url_for('consultation_form', appointment_id=appointment_id))

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        
        appointment = cursor.execute("""
            SELECT id, doctor_id, patient_id 
            FROM Appointment 
            WHERE id = ? AND doctor_id = ? AND status = 'Booked'
        """, (appointment_id, session.get('doctor_id'))).fetchone()

        if not appointment:
            flash('Invalid appointment or status.', 'danger')
            conn.close()
            return redirect(url_for('doctor_dashboard'))

        
        cursor.execute("UPDATE Appointment SET status = 'Completed' WHERE id = ?", (appointment_id,))
        
        
        cursor.execute("""
            INSERT INTO Treatment (appointment_id, diagnosis, prescription, doctor_notes)
            VALUES (?, ?, ?, ?)
        """, (appointment_id, diagnosis, prescription, doctor_notes))
        
        conn.commit()
        flash('Treatment record saved and appointment marked as completed!', 'success')

    except sqlite3.IntegrityError as e:
        conn.rollback()
        flash(f'Error saving treatment (Treatment record may already exist): {e}', 'danger')
    except Exception as e:
        conn.rollback()
        flash(f'An unexpected error occurred: {e}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('doctor_dashboard'))


@app.route('/doctor/cancel_appointment/<int:appointment_id>', methods=['POST'])
@has_role('Doctor')
def cancel_appointment(appointment_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        
        appointment = cursor.execute("""
            SELECT id, date, time 
            FROM Appointment 
            WHERE id = ? AND doctor_id = ? AND status = 'Booked'
        """, (appointment_id, session.get('doctor_id'))).fetchone()
        
        if not appointment:
            flash('Appointment not found or cannot be cancelled.', 'danger')
            conn.close()
            return redirect(url_for('doctor_dashboard'))

        
        cursor.execute("""
            UPDATE DoctorAvailability SET is_booked = 0 
            WHERE doctor_id = ? AND date = ? AND start_time = ?
        """, (session.get('doctor_id'), appointment['date'], appointment['time']))

        
        cursor.execute("UPDATE Appointment SET status = 'Cancelled' WHERE id = ?", (appointment_id,))
        
        conn.commit()
        flash('Appointment successfully cancelled and time slot freed up.', 'info')

    except Exception as e:
        conn.rollback()
        flash(f'An error occurred during cancellation: {e}', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('doctor_dashboard'))


@app.route('/doctor/history/<int:patient_id>', methods=['GET'])
@has_role('Doctor')
def view_patient_history(patient_id):
    conn = get_db_connection()
    
    patient = conn.execute("SELECT name FROM Patient WHERE id = ?", (patient_id,)).fetchone()
    if not patient:
        flash('Patient not found.', 'danger')
        conn.close()
        return redirect(url_for('doctor_dashboard'))

    history = conn.execute("""
        SELECT 
            t.treatment_date, t.diagnosis, t.prescription, t.doctor_notes, 
            d.name AS doctor_name, 
            s.name AS specialization
        FROM Treatment t
        JOIN Appointment a ON t.appointment_id = a.id
        JOIN Doctor d ON a.doctor_id = d.id
        JOIN Specialization s ON d.specialization_id = s.id
        WHERE a.patient_id = ?
        ORDER BY t.treatment_date DESC
    """, (patient_id,)).fetchall()
    
    conn.close()
    
    context = {
        'patient_name': patient['name'],
        'history': history,
        'section_title': f"Treatment History for {patient['name']}"
    }
    return render_template('doctor/patient_history.html', **context)



#Patient routes

@app.route('/patient/register', methods=['GET', 'POST'])
def patient_register():
    if request.method == 'POST':
        name = request.form['name']
        contact_info = request.form['contact_info']
        username = request.form['username']
        password = request.form['password']
        
        
        if not all([name, contact_info, username, password]):
            flash('All fields are required!', 'danger')
            return render_template('patient/register.html', section_title='Patient Registration')

        password_hash = hash_password(password)
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            
            cursor.execute("INSERT INTO User (username, password_hash, role) VALUES (?, ?, 'Patient')",
                           (username, password_hash))
            user_id = cursor.lastrowid
            
            
            cursor.execute("INSERT INTO Patient (user_id, name, contact_info) VALUES (?, ?, ?)",
                           (user_id, name, contact_info))
            
            conn.commit()
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('login'))

        except sqlite3.IntegrityError as e:
            conn.rollback()
            if 'UNIQUE constraint failed: User.username' in str(e):
                flash('Username already exists. Please choose a different one.', 'danger')
            elif 'UNIQUE constraint failed: Patient.contact_info' in str(e):
                flash('Contact information (email) is already registered.', 'danger')
            else:
                flash(f'An unexpected registration error occurred: {e}', 'danger')
            
           
            return render_template('patient/register.html', 
                                   section_title='Patient Registration',
                                   name=name, contact_info=contact_info, username=username)
        
        finally:
            conn.close()

    return render_template('patient/register.html', section_title='Patient Registration')

@app.route('/patient/dashboard')
@has_role('Patient')
def patient_dashboard():
    conn = get_db_connection()
    patient_id = session.get('patient_id')
    
    specializations = conn.execute("SELECT id, name FROM Specialization").fetchall()
    
    
    all_appointments = conn.execute("""
        SELECT 
            a.id, a.date, a.time, a.status, 
            d.name AS doctor_name, 
            s.name AS specialization_name,
            -- Check for a linked treatment record
            EXISTS(SELECT 1 FROM Treatment t WHERE t.appointment_id = a.id) AS has_treatment
        FROM Appointment a
        JOIN Doctor d ON a.doctor_id = d.id
        JOIN Specialization s ON d.specialization_id = s.id
        WHERE a.patient_id = ? 
        ORDER BY a.date DESC, a.time DESC
    """, (patient_id,)).fetchall()

    conn.close()
    
    
    current_date_str = date.today().strftime('%Y-%m-%d')

    upcoming_appointments = [
        appt for appt in all_appointments 
        if appt['status'] == 'Booked' and appt['date'] >= current_date_str
    ]
    history_appointments = [
        appt for appt in all_appointments 
        if appt['status'] != 'Booked' or (appt['status'] == 'Booked' and appt['date'] < current_date_str)
    ]

    context = {
        'patient_id': patient_id,
        'specializations': specializations,
        'upcoming_appointments': upcoming_appointments,
        'history_appointments': history_appointments,
        'today': current_date_str, 
        'section_title': 'Patient Dashboard'
    }
    return render_template('patient/dashboard.html', **context)


@app.route('/patient/find_doctors', methods=['POST'])
@has_role('Patient')
def find_doctors():
    specialization_id = request.form.get('specialization_id')
    appointment_date_str = request.form.get('appointment_date')
    
    if not specialization_id or not appointment_date_str:
        flash('Please select a specialization and a date to search.', 'danger')
        return redirect(url_for('patient_dashboard'))

    conn = get_db_connection()
    
    
    try:
        appointment_date = date.fromisoformat(appointment_date_str)
        if appointment_date < date.today():
            flash('Cannot book appointments for a past date.', 'danger')
            conn.close()
            return redirect(url_for('patient_dashboard'))
    except ValueError:
        flash('Invalid date format.', 'danger')
        conn.close()
        return redirect(url_for('patient_dashboard'))

    
    available_slots = conn.execute("""
        SELECT 
            da.id AS availability_id, 
            da.start_time, 
            d.id AS doctor_id, 
            d.name AS doctor_name, 
            s.name AS specialization_name
        FROM DoctorAvailability da
        JOIN Doctor d ON da.doctor_id = d.id
        JOIN Specialization s ON d.specialization_id = s.id
        WHERE 
            da.date = ? 
            AND s.id = ? 
            AND da.is_booked = 0 
            AND d.is_blacklisted = 0  -- Filter out blacklisted doctors
        ORDER BY d.name, da.start_time
    """, (appointment_date_str, specialization_id)).fetchall()
    
    conn.close()

    if not available_slots:
        flash(f'No available appointments found for {appointment_date_str} in this specialization.', 'info')
        return redirect(url_for('patient_dashboard'))

    
    doctors_with_slots = {}
    for slot in available_slots:
        doctor_id = slot['doctor_id']
        if doctor_id not in doctors_with_slots:
            doctors_with_slots[doctor_id] = {
                'name': slot['doctor_name'],
                'specialization': slot['specialization_name'],
                'slots': []
            }
        doctors_with_slots[doctor_id]['slots'].append({
            'availability_id': slot['availability_id'],
            'time': slot['start_time']
        })
    
    context = {
        'doctors_with_slots': doctors_with_slots,
        'appointment_date': appointment_date_str,
        'specialization_name': available_slots[0]['specialization_name'],
        'section_title': 'Available Appointments'
    }
    return render_template('patient/available_appointments.html', **context)


@app.route('/patient/book_appointment/<int:availability_id>', methods=['POST'])
@has_role('Patient')
def book_appointment(availability_id):
    patient_id = session.get('patient_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    
    slot = cursor.execute("""
        SELECT doctor_id, date, start_time, is_booked 
        FROM DoctorAvailability 
        WHERE id = ?
    """, (availability_id,)).fetchone()

    if not slot or slot['is_booked']:
        conn.close()
        flash('Appointment slot is no longer available or does not exist.', 'danger')
        return redirect(url_for('patient_dashboard'))
        
    doctor_id = slot['doctor_id']
    appointment_date = slot['date']
    appointment_time = slot['start_time']

    try:
        
        cursor.execute("UPDATE DoctorAvailability SET is_booked = 1 WHERE id = ?", (availability_id,))

        
        cursor.execute("""
            INSERT INTO Appointment (patient_id, doctor_id, date, time, status)
            VALUES (?, ?, ?, ?, 'Booked')
        """, (patient_id, doctor_id, appointment_date, appointment_time))
        
        conn.commit()
        flash(f'Appointment successfully booked on {appointment_date} at {appointment_time}!', 'success')

    except sqlite3.IntegrityError as e:
        conn.rollback()
        flash(f'Booking failed due to a database conflict: {e}', 'danger')
    except Exception as e:
        conn.rollback()
        flash(f'An unexpected error occurred during booking: {e}', 'danger')
    finally:
        conn.close()

    return redirect(url_for('patient_dashboard'))


@app.route('/patient/view_treatment/<int:appointment_id>', methods=['GET'])
@has_role('Patient')
def view_patient_treatment(appointment_id):
    conn = get_db_connection()
    patient_id = session.get('patient_id')

    
    appointment = conn.execute("""
        SELECT 
            a.date, a.time, a.status, 
            d.name AS doctor_name, 
            s.name AS specialization_name
        FROM Appointment a
        JOIN Doctor d ON a.doctor_id = d.id
        JOIN Specialization s ON d.specialization_id = s.id
        WHERE a.id = ? AND a.patient_id = ? AND a.status = 'Completed'
    """, (appointment_id, patient_id)).fetchone()

    if not appointment:
        flash('Treatment record not found or appointment is not completed.', 'danger')
        conn.close()
        return redirect(url_for('patient_dashboard'))

    
    treatment = conn.execute("SELECT diagnosis, prescription, treatment_date FROM Treatment WHERE appointment_id = ?", (appointment_id,)).fetchone()
    
    conn.close()
    
    if not treatment:
        flash('Treatment details for this completed appointment are missing.', 'warning')
        return redirect(url_for('patient_dashboard'))

    context = {
        'appointment': appointment,
        'treatment': treatment,
        'section_title': f"Treatment Details: {appointment['date']}"
    }
    return render_template('patient/view_treatment.html', **context)


@app.route('/patient/cancel_booking/<int:appointment_id>', methods=['POST'])
@has_role('Patient')
def patient_cancel_booking(appointment_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    patient_id = session.get('patient_id')
    
    try:
        
        appointment = cursor.execute("""
            SELECT id, doctor_id, date, time 
            FROM Appointment 
            WHERE id = ? AND patient_id = ? AND status = 'Booked'
        """, (appointment_id, patient_id)).fetchone()
        
        if not appointment:
            flash('Appointment not found or cannot be cancelled.', 'danger')
            conn.close()
            return redirect(url_for('patient_dashboard'))

        
        cursor.execute("""
            UPDATE DoctorAvailability SET is_booked = 0 
            WHERE doctor_id = ? AND date = ? AND start_time = ?
        """, (appointment['doctor_id'], appointment['date'], appointment['time']))

        
        cursor.execute("UPDATE Appointment SET status = 'Cancelled' WHERE id = ?", (appointment_id,))
        
        conn.commit()
        flash('Appointment successfully cancelled and time slot freed up.', 'info')

    except Exception as e:
        conn.rollback()
        flash(f'An error occurred during cancellation: {e}', 'danger')
    finally:
        conn.close()
    
    return redirect(url_for('patient_dashboard'))


if __name__ == '__main__':
    create_tables() 
    seed_initial_data() 
    app.run(debug=True)