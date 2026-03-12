from flask import Flask, request, jsonify
from flask_mysqldb import MySQL
from config import Config
import hashlib
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime, timedelta
from flask import request
import pandas as pd
import os
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
from flask_mail import Mail, Message
import random
import traceback

app = Flask(__name__)

# ================= MAIL CONFIGURATION =================

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'himajayenikapati@gmail.com'
app.config['MAIL_PASSWORD'] = 'zzkxzqsvrfeqjyru'


mail = Mail(app)

app.config.from_object(Config)
# MySQL configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'gym_fit_zone'


mysql = MySQL(app)

def log_activity(message):
    cur = mysql.connection.cursor()

    cur.execute("""
        INSERT INTO system_activity(activity)
        VALUES (%s)
    """, (message,))

    mysql.connection.commit()
    cur.close()

# ------------------------------
# Helper Function - Hash Password
# ------------------------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()



# ==========================================
# # Health check for automatic discovery
@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({
        "status": "ok",
        "app": "gym-fitzone",
        "version": "2.0",
        "server_time": str(datetime.now())
    })

# ==========================================
# 1️⃣ REGISTER API (UPDATED WITH ROLE)
# ==========================================
@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json

        name = data['name']
        age = data['age']
        gender = data['gender']
        email = data['email']
        mobile = data['mobile']
        password = hash_password(data['password'])

        role = data.get('role', 'gym_user')

        if role not in ["gym_user", "gym_administrator"]:
            return jsonify({"message": "Invalid role selected"}), 400

        cur = mysql.connection.cursor()

        # Check if email already exists
        cur.execute("SELECT user_id FROM users WHERE email=%s", (email,))
        existing_user = cur.fetchone()

        if existing_user:
            cur.close()
            return jsonify({"message": "Email already registered"}), 400

        cur.execute("""
            INSERT INTO users
            (name, age, gender, email, mobile, password, role, setup_completed, gym_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            name,
            age,
            gender,
            email,
            mobile,
            password,
            role,
            False,   # setup not completed
            None     # gym not selected yet
        ))

        mysql.connection.commit()
        user_id = cur.lastrowid
        cur.close()

        if role == "gym_administrator":
            next_page = "setup_gym"
        else:
            next_page = "select_gym"

        return jsonify({
            "message": "Registration successful",
            "user_id": user_id,
            "role": role,
            "next_page": next_page,
            "name": name,
            "email": email,
            "mobile": mobile,
            "age": age,
            "gender": gender
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

#====================================
#gym setup
@app.route('/setup-gym', methods=['POST'])
def setup_gym():
    data = request.json

    gym_name = data['gym_name']
    address = data['address']
    city = data['city']
    phone = data['phone']
    email = data['email']
    description = data['description']
    gym_admin_id = data['gym_admin_id']

    cur = mysql.connection.cursor()

    # Check if user is gym administrator
    cur.execute("SELECT role FROM users WHERE user_id=%s", (gym_admin_id,))
    user = cur.fetchone()

    if not user or user[0] != "gym_administrator":
        cur.close()
        return jsonify({"message": "Unauthorized"}), 403

    # Check if admin already created a gym
    cur.execute("SELECT gym_id FROM gyms WHERE gym_admin_id=%s", (gym_admin_id,))
    existing = cur.fetchone()

    if existing:
        cur.close()
        return jsonify({"message": "Gym already created"}), 400

    # Insert gym
    cur.execute("""
        INSERT INTO gyms
        (gym_name, address, city, phone, email, description, gym_admin_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (gym_name, address, city, phone, email, description, gym_admin_id))

    mysql.connection.commit()
    gym_id = cur.lastrowid
    cur.close()

    return jsonify({
        "message": "Gym setup completed",
        "next_step": "configure_hours",
        "gym_id": gym_id
    })
# ==========================================
# # ==========================================


#configure Hours 
#=========================================
@app.route('/configure-hours', methods=['POST'])
def configure_hours():
    try:
        data = request.json
        gym_id = data['gym_id']
        sessions = data['sessions']

        cur = mysql.connection.cursor()

        # Remove existing sessions for that gym
        cur.execute("DELETE FROM gym_hours WHERE gym_id=%s", (gym_id,))

        # Insert new sessions
        for session in sessions:
            cur.execute("""
                INSERT INTO gym_hours
                (gym_id, session_type, open_time, close_time)
                VALUES (%s, %s, %s, %s)
            """, (
                gym_id,
                session['session_type'],
                session['open_time'],
                session['close_time']
            ))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Operating hours configured successfully",
            "next_step": "admin_dashboard"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
######################################
#upload history=====================================
########============================
@app.route('/upload-historical-data', methods=['POST'])
def upload_historical_data():
    try:
        print("FORM DATA:", request.form)
        print("FILES DATA:", request.files)

        admin_user_id = request.form.get('admin_user_id')
        file = request.files.get('file')

        if not admin_user_id:
            return jsonify({"error": "admin_user_id missing"}), 400

        if not file:
            return jsonify({"error": "file missing"}), 400

        cur = mysql.connection.cursor()

        # Find gym_id
        cur.execute(
            "SELECT gym_id FROM gyms WHERE gym_admin_id=%s",
            (admin_user_id,)
        )
        gym = cur.fetchone()

        if not gym:
            cur.close()
            return jsonify({"error": "Gym not found for this admin"}), 400

        gym_id = gym[0]

        df = pd.read_excel(file)
        df.dropna(how='all', inplace=True)

        required_cols = ['date', 'slot', 'bookingCount']
        for col in required_cols:
            if col not in df.columns:
                return jsonify({"error": f"Missing required column: '{col}'. Found: {list(df.columns)}"}), 400

        for _, row in df.iterrows():
            try:
                cur.execute("""
                    INSERT INTO historical_bookings
                    (gym_id, booking_date, slot, booking_count)
                    VALUES (%s, %s, %s, %s)
                """, (
                    gym_id,
                    pd.to_datetime(row['date']).date(),
                    row['slot'],
                    int(row['bookingCount'])
                ))
            except Exception as row_e:
                return jsonify({"error": f"Error formatting row data: {str(row_e)}"}), 400

        mysql.connection.commit()
        cur.close()

        return jsonify({"message": "Historical data uploaded successfully"})

    except Exception as e:
        err = traceback.format_exc()
        print("ERROR IN UPLOAD HISTORY:", err)
        return jsonify({"error": err}), 500
    




    #test
    #============
@app.route('/test-upload', methods=['POST'])
def test_upload():
    print("FORM:", request.form)
    print("FILES:", request.files)
    return "Received"



    #################################
    #upload gym members ###################

@app.route('/upload-gym-members', methods=['POST'])
def upload_gym_members():
    try:
        admin_user_id = request.form.get('admin_user_id')
        file = request.files.get('file')

        if not admin_user_id:
            return jsonify({"error": "admin_user_id missing"}), 400

        if not file:
            return jsonify({"error": "file missing"}), 400

        cur = mysql.connection.cursor()

        # Get gym_id
        cur.execute(
            "SELECT gym_id FROM gyms WHERE gym_admin_id=%s",
            (admin_user_id,)
        )
        gym = cur.fetchone()

        if not gym:
            cur.close()
            return jsonify({"error": "Gym not found"}), 400

        gym_id = gym[0]

        df = pd.read_excel(file)
        df.dropna(how='all', inplace=True)

        required_cols = ['memberId', 'name']
        for col in required_cols:
            if col not in df.columns:
                return jsonify({"error": f"Missing required column: '{col}'. Found: {list(df.columns)}"}), 400

        for _, row in df.iterrows():
            try:
                cur.execute("""
                    INSERT INTO gym_member_master
                    (gym_id, member_id, name)
                    VALUES (%s, %s, %s)
                """, (
                    gym_id,
                    row['memberId'],
                    row['name']
                ))
            except Exception as row_e:
                return jsonify({"error": f"Error formatting row data: {str(row_e)}"}), 400

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Gym Member Master uploaded successfully"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    ###==============================
    # set slot capacity=================
@app.route('/set-slot-capacity', methods=['POST'])
def set_slot_capacity():
    try:
        data = request.json
        admin_user_id = data.get('admin_user_id')
        capacity = data.get('capacity')

        if not admin_user_id:
            return jsonify({"error": "admin_user_id missing"}), 400

        if not capacity:
            return jsonify({"error": "capacity missing"}), 400

        cur = mysql.connection.cursor()

        # Update capacity for this admin's gym
        cur.execute("""
            UPDATE gyms
            SET slot_capacity = %s
            WHERE gym_admin_id = %s
        """, (capacity, admin_user_id))
         
         # 2️⃣ Mark setup as completed (ADD THIS HERE)
        cur.execute("""
            UPDATE users
            SET setup_completed = TRUE
            WHERE user_id = %s
        """, (admin_user_id,))


        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Slot capacity set successfully"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    



    ###=============================================
@app.route('/gym-dashboard', methods=['POST'])
def gym_dashboard():
    try:
        data = request.json
        admin_user_id = data.get('admin_user_id')

        if not admin_user_id:
            return jsonify({"error": "admin_user_id missing"}), 400

        cur = mysql.connection.cursor()

        # Get gym_id, details and admin name
        cur.execute("""
            SELECT g.gym_id, g.gym_name, g.address, g.city, u.name 
            FROM gyms g
            JOIN users u ON g.gym_admin_id = u.user_id
            WHERE g.gym_admin_id = %s
        """, (admin_user_id,))
        gym = cur.fetchone()

        if not gym:
            cur.close()
            return jsonify({"error": "Gym not found"}), 400

        gym_id = gym[0]
        gym_name = gym[1]
        gym_location = gym[2]
        gym_city = gym[3]
        admin_name = gym[4]

        # 1️⃣ Total Members
        cur.execute(
            "SELECT COUNT(*) FROM gym_member_master WHERE gym_id=%s",
            (gym_id,)
        )
        total_members = cur.fetchone()[0]

        # 2️⃣ Today's Bookings
        cur.execute("""
            SELECT COUNT(*) FROM bookings
            WHERE gym_id=%s AND DATE(booking_date)=CURDATE()
        """, (gym_id,))
        todays_bookings = cur.fetchone()[0]

        # 3️⃣ Total Bookings
        cur.execute(
            "SELECT COUNT(*) FROM bookings WHERE gym_id=%s",
            (gym_id,)
        )
        total_bookings = cur.fetchone()[0]

        # 4️⃣ Peak Time
        cur.execute("""
            SELECT time_slot, COUNT(*) as count 
            FROM bookings 
            WHERE gym_id=%s 
            GROUP BY time_slot 
            ORDER BY count DESC 
            LIMIT 1
        """, (gym_id,))
        peak_row = cur.fetchone()
        peak_time = peak_row[0] if peak_row else "N/A"

        # 5️⃣ Time Slots Count
        cur.execute(
            "SELECT COUNT(*) FROM gym_hours WHERE gym_id=%s",
            (gym_id,)
        )
        time_slots = cur.fetchone()[0]

        # 6️⃣ Popular Workouts
        cur.execute("""
            SELECT workout_type, COUNT(*) as count 
            FROM bookings 
            WHERE gym_id=%s 
            GROUP BY workout_type 
            ORDER BY count DESC 
            LIMIT 3
        """, (gym_id,))
        workout_rows = cur.fetchall()
        
        popular_workouts = []
        if total_bookings > 0:
            for row in workout_rows:
                workout_name = row[0]
                count = row[1]
                percentage = f"{int((count / total_bookings) * 100)}%"
                popular_workouts.append({
                    "workout": workout_name,
                    "percentage": percentage
                })

        # 7️⃣ Peak Hours Analysis (Counts by time slot)
        cur.execute("""
            SELECT time_slot, COUNT(*) as count 
            FROM bookings 
            WHERE gym_id=%s 
            GROUP BY time_slot 
            ORDER BY time_slot ASC 
            LIMIT 5
        """, (gym_id,))
        peak_hour_rows = cur.fetchall()
        
        peak_hours = []
        if peak_hour_rows:
            max_count = max([row[1] for row in peak_hour_rows])
            max_count = max_count if max_count > 0 else 1
            for row in peak_hour_rows:
                peak_hours.append({
                    "time_slot": row[0],
                    "weight": float(row[1]) / float(max_count)
                })

        # 8️⃣ Public Holidays
        cur.execute("SELECT holiday_date FROM gym_holidays WHERE gym_id=%s", (gym_id,))
        public_holidays = [row[0] for row in cur.fetchall()]

        # 9️⃣ Morning Only Days
        cur.execute("SELECT special_date FROM morning_only_days WHERE gym_id=%s", (gym_id,))
        morning_only_days = [row[0] for row in cur.fetchall()]

        cur.close()

        return jsonify({
            "gym_id": gym_id,
            "gym_name": gym_name,
            "location": gym_location,
            "city": gym_city,
            "admin_name": admin_name,
            "total_members": total_members,
            "todays_bookings": todays_bookings,
            "total_bookings": total_bookings,
            "time_slots": time_slots,
            "peak_time": peak_time,
            "weekly_growth": "+12%",
            "monthly_growth": "+8%",
            "popular_workouts": popular_workouts,
            "peak_hours": peak_hours,
            "public_holidays": public_holidays,
            "morning_only_days": morning_only_days
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


###################################################
#===========================================================
@app.route('/get-members', methods=['POST'])
def get_members():
    try:
        data = request.json
        admin_user_id = data.get('admin_user_id')

        if not admin_user_id:
            return jsonify({"error": "admin_user_id missing"}), 400

        cur = mysql.connection.cursor()

        # Get gym_id
        cur.execute(
            "SELECT gym_id FROM gyms WHERE gym_admin_id=%s",
            (admin_user_id,)
        )
        gym = cur.fetchone()

        if not gym:
            cur.close()
            return jsonify({"error": "Gym not found"}), 400

        gym_id = gym[0]

        # Get members with their registration details if they exist
        cur.execute("""
            SELECT m.member_id, 
                   COALESCE(u.name, m.name) as name,
                   u.email, u.mobile, u.age, u.gender
            FROM gym_member_master m
            LEFT JOIN users u ON m.member_id = u.member_id AND u.gym_id = m.gym_id
            WHERE m.gym_id=%s
        """, (gym_id,))

        members = cur.fetchall()
        cur.close()

        member_list = []
        for m in members:
            member_list.append({
                "member_id": m[0],
                "name": m[1],
                "email": m[2] if m[2] else "Not Registered",
                "mobile": m[3] if m[3] else "N/A",
                "age": m[4] if m[4] else "N/A",
                "gender": m[5] if m[5] else "N/A"
            })

        return jsonify({
            "total_members": len(member_list),
            "members": member_list
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    #=========================================
@app.route('/add-member', methods=['POST'])
def add_member():
    try:
        data = request.json
        admin_user_id = data.get('admin_user_id')
        member_id = data.get('member_id')
        name = data.get('name')

        if not all([admin_user_id, member_id, name]):
            return jsonify({"error": "Missing fields"}), 400

        cur = mysql.connection.cursor()

        # Get gym_id
        cur.execute(
            "SELECT gym_id FROM gyms WHERE gym_admin_id=%s",
            (admin_user_id,)
        )
        gym = cur.fetchone()

        if not gym:
            cur.close()
            return jsonify({"error": "Gym not found"}), 400

        gym_id = gym[0]

        # Insert new member
        cur.execute("""
            INSERT INTO gym_member_master (gym_id, member_id, name)
            VALUES (%s, %s, %s)
        """, (gym_id, member_id, name))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Member added successfully"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    


    #=======================================
@app.route('/update-gym-hours', methods=['POST'])
def update_gym_hours():
    try:
        data = request.json
        admin_user_id = data.get('admin_user_id')
        sessions = data.get('sessions')

        cur = mysql.connection.cursor()

        cur.execute(
            "SELECT gym_id FROM gyms WHERE gym_admin_id=%s",
            (admin_user_id,)
        )
        gym = cur.fetchone()

        if not gym:
            return jsonify({"error": "Gym not found"}), 400

        gym_id = gym[0]

        # Delete old hours
        cur.execute("DELETE FROM gym_hours WHERE gym_id=%s", (gym_id,))

        # Insert new hours
        for s in sessions:
            cur.execute("""
                INSERT INTO gym_hours
                (gym_id, session_name, opening_time, closing_time)
                VALUES (%s, %s, %s, %s)
            """, (
                gym_id,
                s['session_name'],
                s['opening_time'],
                s['closing_time']
            ))

        mysql.connection.commit()
        cur.close()

        return jsonify({"message": "Gym hours updated"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
#========================================================
@app.route('/add-holiday', methods=['POST'])
def add_holiday():
    data = request.json
    admin_user_id = data.get('admin_user_id')
    holiday_date = data.get('holiday_date')

    cur = mysql.connection.cursor()

    cur.execute(
        "SELECT gym_id FROM gyms WHERE gym_admin_id=%s",
        (admin_user_id,)
    )
    gym = cur.fetchone()

    gym_id = gym[0]

    cur.execute("""
        INSERT INTO gym_holidays (gym_id, holiday_date)
        VALUES (%s, %s)
    """, (gym_id, holiday_date))

    mysql.connection.commit()
    cur.close()

    return jsonify({"message": "Holiday added"})

#morning session=======
@app.route('/add-morning-only', methods=['POST'])
def add_morning_only():
    data = request.json
    admin_user_id = data.get('admin_user_id')
    special_date = data.get('special_date')

    cur = mysql.connection.cursor()

    cur.execute(
        "SELECT gym_id FROM gyms WHERE gym_admin_id=%s",
        (admin_user_id,)
    )
    gym = cur.fetchone()

    gym_id = gym[0]

    cur.execute("""
        INSERT INTO morning_only_days (gym_id, special_date)
        VALUES (%s, %s)
    """, (gym_id, special_date))

    mysql.connection.commit()
    cur.close()

    return jsonify({"message": "Morning-only day added"})

#===================================
@app.route('/get-gym-info', methods=['POST'])
def get_gym_info():
    try:
        data = request.json
        admin_user_id = data.get('admin_user_id')

        if not admin_user_id:
            return jsonify({"error": "admin_user_id missing"}), 400

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT gym_id, gym_name, location, city, status
            FROM gyms
            WHERE gym_admin_id=%s
        """, (admin_user_id,))

        gym = cur.fetchone()

        if not gym:
            cur.close()
            return jsonify({"error": "Gym not found"}), 400

        gym_data = {
            "gym_id": gym[0],
            "gym_name": gym[1],
            "location": gym[2],
            "city": gym[3],
            "status": gym[4]
        }

        cur.close()

        return jsonify(gym_data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


#===============================
# get registered gyms

@app.route('/get-registered-gyms', methods=['GET'])
def get_registered_gyms():
    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT gym_id, gym_name, city, location
        FROM gyms
    """)

    gyms = cur.fetchall()
    cur.close()

    gym_list = []

    for g in gyms:
        gym_list.append({
            "gym_id": g[0],
            "gym_name": g[1],
            "city": g[2],
            "location": g[3],
            "gym_code": f"GYM{g[0]:03d}"
        })

    return jsonify(gym_list)

##====================
#gym+ enter id=============
@app.route('/verify-member', methods=['POST'])
def verify_member():
    try:
        data = request.json
        user_id = data.get('user_id')
        gym_id = data.get('gym_id')
        member_id = data.get('member_id')

        if not all([user_id, gym_id, member_id]):
            return jsonify({"error": "Missing fields"}), 400

        cur = mysql.connection.cursor()

        # 🔹 1️⃣ Check user exists and is gym_user
        cur.execute("""
            SELECT role FROM users WHERE user_id=%s
        """, (user_id,))
        user = cur.fetchone()

        if not user:
            cur.close()
            return jsonify({"error": "User does not exist"}), 400

        if user[0] != "gym_user":
            cur.close()
            return jsonify({"error": "Only gym users can verify"}), 400

        # 🔹 2️⃣ Check member exists in selected gym
        cur.execute("""
            SELECT member_id FROM gym_member_master
            WHERE gym_id=%s AND member_id=%s
        """, (gym_id, member_id))

        member = cur.fetchone()

        if not member:
            cur.close()
            return jsonify({"error": "Invalid Member ID for selected gym"}), 400

        # 🔹 3️⃣ Update user with gym_id and member_id
        cur.execute("""
            UPDATE users
            SET gym_id=%s, member_id=%s, setup_completed=TRUE
            WHERE user_id=%s
        """, (gym_id, member_id, user_id))

        

        mysql.connection.commit()
        cur.close()

        # 🔹 4️⃣ Get gym name and location to return to frontend
        cur = mysql.connection.cursor()
        cur.execute("SELECT gym_name, location, city FROM gyms WHERE gym_id=%s", (gym_id,))
        gym_data = cur.fetchone()
        cur.close()

        gym_name = gym_data[0] if gym_data else "Unknown Gym"
        gym_location = f"{gym_data[1]}, {gym_data[2]}" if gym_data else ""

        return jsonify({
            "message": "Verification successful",
            "next_page": "user_dashboard",
            "gym_name": gym_name,
            "gym_location": gym_location
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

    #user home ======================================
@app.route('/user-home/<int:user_id>', methods=['GET'])
def user_home(user_id):
    try:
        cur = mysql.connection.cursor()

        # 1️⃣ Get user & gym info
        cur.execute("""
            SELECT u.name, u.gym_id, g.gym_name
            FROM users u
            JOIN gyms g ON u.gym_id = g.gym_id
            WHERE u.user_id = %s
        """, (user_id,))
        
        user = cur.fetchone()

        if not user:
            return jsonify({"error": "User not found"}), 404

        name, gym_id, gym_name = user

        today = pd.to_datetime("today").date()

        # 2️⃣ Get dynamic slots & bookings logic
        cur.execute("SELECT slot_capacity FROM gyms WHERE gym_id = %s", (gym_id,))
        capacity_row = cur.fetchone()
        capacity = capacity_row[0] if capacity_row else 10

        cur.execute("SELECT open_time, close_time FROM gym_hours WHERE gym_id = %s", (gym_id,))
        operating_hours = cur.fetchall()

        slots = []
        for session in operating_hours:
            # timedelta to start/end hours
            start_hour = int(session[0].total_seconds() // 3600) if not isinstance(session[0], str) else int(session[0].split(':')[0])
            end_hour = int(session[1].total_seconds() // 3600) if not isinstance(session[1], str) else int(session[1].split(':')[0])
            
            for hour in range(start_hour, end_hour):
                slot_time = f"{hour:02d}:00"
                
                cur.execute("""
                    SELECT COUNT(*) FROM bookings
                    WHERE gym_id=%s AND booking_date=%s AND time_slot=%s AND booking_status='active'
                """, (gym_id, today, slot_time))
                booked = cur.fetchone()[0]
                
                slots.append((slot_time, capacity, booked))

        next_available = None
        peak_slot = None
        highest_percent = 0

        for slot in slots:
            slot_time = slot[0]
            capacity = slot[1]
            booked = slot[2]

            percent = (booked / capacity) * 100 if capacity else 0

            # Find next available slot
            if booked < capacity and not next_available:
                next_available = slot_time

            # Find peak slot
            if percent > highest_percent:
                highest_percent = percent
                peak_slot = slot_time

        # 3️⃣ Decide crowd level
        if highest_percent < 50:
            crowd_level = "Low"
        elif highest_percent < 75:
            crowd_level = "Medium"
        else:
            crowd_level = "High"

        cur.close()

        return jsonify({
            "user_name": name,
            "gym_name": gym_name,
            "current_crowd_level": crowd_level,
            "next_available_slot": next_available,
            "peak_slot": peak_slot,
            "peak_message": f"Expected peak crowd at {peak_slot}"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500



# Get slot Availiability=========================================================
@app.route('/get-slots', methods=['POST'])
def get_slots():
    try:
        data = request.json
        gym_id = data.get('gym_id')
        selected_date = data.get('date')

        cur = mysql.connection.cursor()

        # 1. Check for Holiday
        cur.execute("SELECT id FROM gym_holidays WHERE gym_id=%s AND holiday_date=%s", (gym_id, selected_date))
        if cur.fetchone():
            cur.close()
            return jsonify([]) # No slots on holidays

        # 2. Check for Morning-Only
        cur.execute("SELECT id FROM morning_only_days WHERE gym_id=%s AND special_date=%s", (gym_id, selected_date))
        is_morning_only = cur.fetchone() is not None

        # 🔹 Get global slot capacity for this gym from gyms table
        cur.execute("SELECT slot_capacity FROM gyms WHERE gym_id=%s", (gym_id,))
        capacity_row = cur.fetchone()
        capacity = capacity_row[0] if capacity_row else 10 # Default to 10 if not found

        # 🔹 Get gym operating hours (multiple sessions possible)
        cur.execute("""
            SELECT session_type, open_time, close_time
            FROM gym_hours
            WHERE gym_id=%s
        """, (gym_id,))
        operating_sessions = cur.fetchall()

        response = []

        # 🔹 Generate slots based on operating hours
        for session in operating_sessions:
            session_type = session[0]
            open_time = session[1] # e.g. 06:00:00
            close_time = session[2] # e.g. 11:00:00

            # Convert to hours
            try:
                # open_time and close_time are timedelta objects in mysql-connector
                # but it's easier to handle them as strings or use their .seconds properties
                # Let's assume they are strings or can be converted to hours
                
                # Handling timedelta vs string
                if isinstance(open_time, str):
                    start_hour = int(open_time.split(':')[0])
                else: # timedelta
                    start_hour = int(open_time.total_seconds() // 3600)

                if isinstance(close_time, str):
                    end_hour = int(close_time.split(':')[0])
                else: # timedelta
                    end_hour = int(close_time.total_seconds() // 3600)

                for hour in range(start_hour, end_hour):
                    slot_time = f"{hour:02d}:00"

                    # 🔹 Respect morning-only logic: skip afternoon/evening slots if it's a morning-only day
                    if is_morning_only and hour >= 12:
                        continue

                    # 🔹 Count bookings for this specific slot and date
                    cur.execute("""
                        SELECT COUNT(*)
                        FROM bookings
                        WHERE gym_id=%s
                        AND booking_date=%s
                        AND time_slot=%s
                        AND booking_status='active'
                    """, (gym_id, selected_date, slot_time))
                    
                    booked = cur.fetchone()[0]
                    
                    # 🔹 Color Code Logic Based on Capacity
                    percentage = (booked / capacity) * 100 if capacity > 0 else 0
                    if percentage < 50:
                        color = "green"
                        status = "Available"
                    elif percentage < 85:
                        color = "yellow"
                        status = "Filling Fast"
                    else:
                        color = "red"
                        status = "Almost Full"

                    # Check if slot is full
                    if booked >= capacity:
                        status = "Full"
                        color = "red"

                    response.append({
                        "slot": slot_time,
                        "booked": booked,
                        "capacity": capacity,
                        "color": color,
                        "status": status
                    })
            except Exception as e:
                print(f"Error generating slots for session: {e}")
                continue

        # Sort slots by time
        response.sort(key=lambda x: x['slot'])

        cur.close()
        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    # ==========================================================================
    #Ai prediction===================
def train_model(gym_id):
    cur = mysql.connection.cursor()

    # 1️⃣ Historical Data
    cur.execute("""
        SELECT booking_date, slot, booking_count
        FROM historical_bookings
        WHERE gym_id=%s
    """, (gym_id,))
    historical = cur.fetchall()

    # 2️⃣ Aggregate Current Booking Data
    cur.execute("""
        SELECT booking_date, time_slot, COUNT(*)
        FROM bookings
        WHERE gym_id=%s
        AND booking_status='active'
        GROUP BY booking_date, time_slot
    """, (gym_id,))
    current_data = cur.fetchall()

    cur.close()

    if not historical and not current_data:
        return None, None

    import pandas as pd

    # Convert to same format
    df1 = pd.DataFrame(historical, columns=["booking_date", "slot", "booking_count"])
    df2 = pd.DataFrame(current_data, columns=["booking_date", "slot", "booking_count"])

    df = pd.concat([df1, df2], ignore_index=True)

    df["booking_date"] = pd.to_datetime(df["booking_date"])
    df["day_of_week"] = df["booking_date"].dt.dayofweek
    df["month"] = df["booking_date"].dt.month
    df["is_weekend"] = df["day_of_week"].apply(lambda x: 1 if x >= 5 else 0)

    from sklearn.preprocessing import LabelEncoder
    from sklearn.ensemble import RandomForestRegressor

    le = LabelEncoder()
    df["slot_encoded"] = le.fit_transform(df["slot"])

    X = df[["day_of_week", "month", "is_weekend", "slot_encoded"]]
    y = df["booking_count"]

    model = RandomForestRegressor()
    model.fit(X, y)

    return model, le

#============================================================================================
#prediction==================================================================================
@app.route('/slot-insights', methods=['POST'])
def slot_insights():
    try:
        data = request.json
        gym_id = data.get('gym_id')
        selected_date = data.get('date')
        slot_time = data.get('slot')

        cur = mysql.connection.cursor()

        # 1️⃣ Total bookings
        cur.execute("""
            SELECT COUNT(*)
            FROM bookings
            WHERE gym_id=%s
            AND booking_date=%s
            AND time_slot=%s
        """, (gym_id, selected_date, slot_time))
        total_bookings = cur.fetchone()[0]

        # 2️⃣ Separate workouts
        cur.execute("""
            SELECT workout_type, COUNT(*)
            FROM bookings
            WHERE gym_id=%s
            AND booking_date=%s
            AND time_slot=%s
            AND workout_type NOT LIKE '%%+%%'
            GROUP BY workout_type
        """, (gym_id, selected_date, slot_time))
        separate = cur.fetchall()

        # 3️⃣ Combo workouts
        cur.execute("""
            SELECT workout_type, COUNT(*)
            FROM bookings
            WHERE gym_id=%s
            AND booking_date=%s
            AND time_slot=%s
            AND workout_type LIKE '%%+%%'
            GROUP BY workout_type
        """, (gym_id, selected_date, slot_time))
        combos = cur.fetchall()

        cur.close()

        separate_list = []
        for s in separate:
            separate_list.append({
                "workout": s[0],
                "count": s[1]
            })

        combo_list = []
        for c in combos:
            combo_list.append({
                "combo": c[0],
                "count": c[1]
            })

        # 4️⃣ AI Prediction
        model, le = train_model(gym_id)

        if model is None:
            predicted = total_bookings
        else:
            selected_date_obj = pd.to_datetime(selected_date)
            day_of_week = selected_date_obj.dayofweek
            month = selected_date_obj.month
            is_weekend = 1 if day_of_week >= 5 else 0

            try:
                slot_encoded = le.transform([slot_time])[0]
                predicted = model.predict([[
                    day_of_week,
                    month,
                    is_weekend,
                    slot_encoded
                ]])[0]
                predicted = round(predicted)
            except:
                predicted = total_bookings

        # 5️⃣ Trend logic
        if predicted > total_bookings:
            trend = "Crowd expected to increase."
        elif predicted == total_bookings:
            trend = "Stable trend."
        else:
            trend = "Less crowded than usual."

        # 6️⃣ Log AI prediction vs actual
        cur = mysql.connection.cursor()

        cur.execute("""
            INSERT INTO ai_prediction_logs
            (gym_id, slot, predicted_count, actual_count, prediction_date)
            VALUES (%s,%s,%s,%s,%s)
        """, (gym_id, slot_time, predicted, total_bookings, selected_date))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "total_bookings": total_bookings,
            "combo_bookings": combo_list,
            "separate_bookings": separate_list,
            "ai_prediction": predicted,
            "trend_message": trend
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


#===============================================================================
#confirm booking
@app.route('/confirm-booking', methods=['POST'])
def confirm_booking():
    try:
        data = request.json

        user_id = data.get('user_id')
        gym_id = data.get('gym_id')
        booking_date = data.get('booking_date')
        time_slot = data.get('time_slot')
        workouts = data.get('workouts')  # dictionary
        duration = data.get('duration_minutes')

        # 🔒 Basic validations
        if not all([user_id, gym_id, booking_date, time_slot, workouts, duration]):
            return jsonify({"error": "Missing required fields"}), 400

        if not workouts:
            return jsonify({"error": "No workouts selected"}), 400

        # 🔒 Prevent past date booking
        selected_date = pd.to_datetime(booking_date).date()
        today = pd.to_datetime("today").date()

        if selected_date < today:
            return jsonify({"error": "Cannot book past dates"}), 400

        cur = mysql.connection.cursor()

        # 🔒 Check for Holiday (Second layer of defense)
        cur.execute("SELECT id FROM gym_holidays WHERE gym_id=%s AND holiday_date=%s", (gym_id, booking_date))
        if cur.fetchone():
            cur.close()
            return jsonify({"error": "The gym is closed on this day for a holiday."}), 400

        # 🔒 Check for Morning-Only (Second layer of defense)
        cur.execute("SELECT id FROM morning_only_days WHERE gym_id=%s AND special_date=%s", (gym_id, selected_date))
        if cur.fetchone():
            try:
                # Logic: assume afternoon starts after 12:00
                start_hour = int(time_slot.split(':')[0])
                if start_hour >= 12:
                    cur.close()
                    return jsonify({"error": "This day is designated for morning sessions only."}), 400
            except:
                pass

        # 🔒 Prevent double booking
        cur.execute("""
            SELECT booking_id
            FROM bookings
            WHERE user_id=%s
            AND booking_date=%s
            AND time_slot=%s
            AND booking_status='active'
        """, (user_id, booking_date, time_slot))

        existing = cur.fetchone()

        if existing:
            cur.close()
            return jsonify({
                "error": "You have already booked this slot."
            }), 400

        # 🔒 Get slot capacity
        # 🔒 Get slot capacity (FROM gyms TABLE)
        cur.execute("SELECT slot_capacity FROM gyms WHERE gym_id = %s", (gym_id,))
        cap_res = cur.fetchone()
        
        if not cap_res:
            cur.close()
            return jsonify({"error": "Gym configuration not found."}), 400
            
        capacity = cap_res[0]

        # 🔒 Count existing bookings
        cur.execute("""
            SELECT COUNT(*)
            FROM bookings
            WHERE gym_id=%s
            AND booking_date=%s
            AND time_slot=%s
            AND booking_status='active'
        """, (gym_id, booking_date, time_slot))

        booked = cur.fetchone()[0]

        if booked >= capacity:
            cur.close()
            return jsonify({
                "error": "Slot is full. Booking not allowed."
            }), 400

        # ✅ Create summary (Cardio + Chest + Tricep)
        categories = list(workouts.keys())
        summary_string = " + ".join(categories)

        # ✅ Create detailed breakdown
        breakdown_list = []
        for category, exercises in workouts.items():
            exercise_string = ", ".join(exercises)
            breakdown_list.append(f"{category} : {exercise_string}")

        breakdown_string = " | ".join(breakdown_list)

        # ✅ Insert booking
        cur.execute("""
            INSERT INTO bookings
            (user_id, gym_id, booking_date, day_of_week,
             time_slot, workout_type, workout_zones,
             equipment_selected, duration_minutes, booking_status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            user_id,
            gym_id,
            booking_date,
            pd.to_datetime(booking_date).day_name(),
            time_slot,
            summary_string,
            breakdown_string,
            "",
            duration,
            "active"
        ))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Booking Confirmed Successfully",
            "summary": summary_string,
            "details": breakdown_string
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

#== History=======================================================================
@app.route('/history/<int:user_id>', methods=['GET'])
def history(user_id):
    try:
        cur = mysql.connection.cursor()

        # 🕒 0️⃣ Auto-expiry: Mark passed slots as 'expired'
        cur.execute("""
            UPDATE bookings 
            SET booking_status = 'expired' 
            WHERE user_id = %s 
            AND booking_status = 'active'
            AND (
                booking_date < CURDATE()
                OR (
                    booking_date = CURDATE() 
                    AND ADDTIME(STR_TO_DATE(LEFT(time_slot, 5), '%H:%i'), SEC_TO_TIME(duration_minutes * 60)) < CURTIME()
                )
            )
        """, (user_id,))
        mysql.connection.commit()

        cur.execute("""
            SELECT booking_id,
                   booking_date,
                   time_slot,
                   workout_type,
                   workout_zones,
                   duration_minutes,
                   booking_status
            FROM bookings
            WHERE user_id=%s
            ORDER BY booking_date DESC
        """, (user_id,))

        rows = cur.fetchall()
        cur.close()

        result = []

        for row in rows:
            booking_id = row[0]
            booking_date = row[1]
            time_slot = row[2]
            summary = row[3]           # Cardio + Chest + Tricep
            details = row[4]           # Chest - Bench Press...
            duration = row[5]
            status = row[6]

            # Optional: Cancel allowed only for future bookings
            from datetime import date
            today = date.today()

            if booking_date >= today and status == "active":
                cancel_allowed = True
            else:
                cancel_allowed = False

            result.append({
                "booking_id": booking_id,
                "date": str(booking_date),
                "slot": time_slot,
                "summary": summary,
                "details": details,
                "duration_minutes": duration,
                "status": status,
                "cancel_allowed": cancel_allowed
            })

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

#=====================================
@app.route('/cancel-booking', methods=['POST'])
def cancel_booking():
    try:
        data = request.json
        booking_id = data.get('booking_id')
        user_id = data.get('user_id')

        cur = mysql.connection.cursor()

        # Ensure booking belongs to user
        cur.execute("""
            SELECT booking_status
            FROM bookings
            WHERE booking_id=%s AND user_id=%s
        """, (booking_id, user_id))

        booking = cur.fetchone()

        if not booking:
            cur.close()
            return jsonify({"error": "Booking not found"}), 404

        if booking[0] == "cancelled":
            cur.close()
            return jsonify({"error": "Already cancelled"}), 400

        # Update status
        cur.execute("""
            UPDATE bookings
            SET booking_status='cancelled'
            WHERE booking_id=%s
        """, (booking_id,))

        mysql.connection.commit()
        cur.close()

        return jsonify({"message": "Booking cancelled successfully"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500



#=================================================================================
# 2️⃣ LOGIN API (UPDATED WITH ROLE)
# ==========================================
@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        email = data['email']
        password = hash_password(data['password'])

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT user_id, role, gym_id, setup_completed, name, email, mobile, age, gender, member_id
            FROM users
            WHERE email=%s AND password=%s
        """, (email, password))

        user = cur.fetchone()
        cur.close()

        if not user:
            return jsonify({"message": "Invalid credentials"}), 401

        user_id = user[0]
        role = user[1]
        gym_id = user[2]
        setup_completed = user[3]
        name = user[4]
        user_email = user[5]
        mobile = user[6]
        age = user[7]
        gender = user[8]
        member_id = user[9]

        # Get gym name and location if gym_id exists
        gym_name = None
        gym_location = None
        if gym_id:
            cur = mysql.connection.cursor()
            cur.execute("SELECT gym_name, location, city FROM gyms WHERE gym_id=%s", (gym_id,))
            gym_data = cur.fetchone()
            if gym_data:
                gym_name = gym_data[0]
                gym_location = f"{gym_data[1]}, {gym_data[2]}"
            cur.close()

        # 🔥 ADMIN FLOW
        if role == "gym_administrator":
            if not setup_completed:
                next_page = "setup_gym"
            else:
                next_page = "gym_dashboard"

        # 🔥 GYM USER FLOW
        elif role == "gym_user":
            if not setup_completed:
                next_page = "select_gym"
            else:
                next_page = "user_dashboard"

        return jsonify({
            "message": "Login successful",
            "user_id": user_id,
            "role": role,
            "next_page": next_page,
            "name": name,
            "email": user_email,
            "mobile": mobile,
            "age": age,
            "gender": gender,
            "gym_id": gym_id,
            "gym_name": gym_name,
            "gym_location": gym_location,
            "member_id": member_id
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

#forgot password api
@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    try:
        data = request.json
        email = data['email']

        cur = mysql.connection.cursor()

        cur.execute("SELECT user_id FROM users WHERE email=%s", (email,))
        user = cur.fetchone()

        if not user:
            return jsonify({"message": "Email not found"}), 404

        # Generate OTP
        otp = str(random.randint(100000, 999999))

        expiry_time = datetime.now() + timedelta(minutes=10)

        # Store OTP in DB
        cur.execute("""
            UPDATE users 
            SET reset_token=%s, token_expiry=%s
            WHERE email=%s
        """, (otp, expiry_time, email))

        mysql.connection.commit()
        cur.close()

        # Send email
        msg = Message(
            subject="FitZone Password Reset OTP",
            sender=app.config['MAIL_USERNAME'],
            recipients=[email]
        )

        msg.body = f"""
Hello,

Your OTP for resetting your Gym FitZone account password is:

{otp}

This OTP will expire in 10 minutes.

If you did not request this, please ignore this email.

FitZone Support
"""

        mail.send(msg)

        return jsonify({
            "message": "OTP sent successfully"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    


#===============================================================
# reset password

@app.route('/reset-password', methods=['POST'])
def reset_password():
    try:
        data = request.json

        email = data['email']
        otp = data['otp']
        new_password = hash_password(data['password'])

        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT reset_token, token_expiry
            FROM users
            WHERE email=%s
        """, (email,))

        user = cur.fetchone()

        if not user:
            return jsonify({"message": "Invalid email"}), 404

        stored_otp, expiry = user

        if otp != stored_otp:
            return jsonify({"message": "Invalid OTP"}), 400

        if datetime.now() > expiry:
            return jsonify({"message": "OTP expired"}), 400

        # Update password
        cur.execute("""
            UPDATE users
            SET password=%s,
                reset_token=NULL,
                token_expiry=NULL
            WHERE email=%s
        """, (new_password, email))

        mysql.connection.commit()
        cur.close()

        return jsonify({
            "message": "Password reset successful"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    #==================================================
#user profile =====================================
@app.route('/user-profile/<int:user_id>', methods=['GET'])
def user_profile(user_id):
    try:
        cur = mysql.connection.cursor()

        # 1️⃣ Get user details
        cur.execute("""
            SELECT u.name, u.email, u.mobile, u.age, u.gender,
                   u.member_id, u.gym_id, u.role,
                   g.gym_name, g.address, g.city
            FROM users u
            LEFT JOIN gyms g ON u.gym_id = g.gym_id
            WHERE u.user_id = %s
        """, (user_id,))
        
        user = cur.fetchone()

        if not user:
            return jsonify({"error": "User not found"}), 404

        name, email, mobile, age, gender, member_id, gym_id, role, gym_name, address, city = user

        # 🔹 Automagic Backfill: If member_id is missing but we have a gym, try to find it by name
        if not member_id and gym_id:
            cur.execute("""
                SELECT member_id FROM gym_member_master 
                WHERE gym_id=%s AND name=%s
            """, (gym_id, name))
            matching_members = cur.fetchall()
            if len(matching_members) == 1:
                member_id = matching_members[0][0]
                # Update the users table for future calls
                cur.execute("UPDATE users SET member_id=%s WHERE user_id=%s", (member_id, user_id))
                mysql.connection.commit()

        # 🕒 0️⃣ Auto-expiry: Sync old slots before counting
        cur.execute("""
            UPDATE bookings 
            SET booking_status = 'expired' 
            WHERE user_id = %s 
            AND booking_status = 'active'
            AND (
                booking_date < CURDATE()
                OR (
                    booking_date = CURDATE() 
                    AND ADDTIME(STR_TO_DATE(LEFT(time_slot, 5), '%H:%i'), SEC_TO_TIME(duration_minutes * 60)) < CURTIME()
                )
            )
        """, (user_id,))
        mysql.connection.commit()

        # 2️⃣ Total bookings (excluding cancelled)
        cur.execute("""
            SELECT COUNT(*)
            FROM bookings
            WHERE user_id=%s AND booking_status != 'cancelled'
        """, (user_id,))
        total_bookings = cur.fetchone()[0]

        # 3️⃣ Active bookings (future/today bookings that are NOT cancelled)
        cur.execute("""
            SELECT COUNT(*)
            FROM bookings
            WHERE user_id=%s
            AND booking_date >= CURDATE()
            AND booking_status = 'active'
        """, (user_id,))
        active_bookings = cur.fetchone()[0]

        cur.close()

        return jsonify({
            "name": name,
            "role": role,
            "email": email,
            "mobile": mobile,
            "age": age,
            "gender": gender,
            "gym": {
                "gym_id": gym_id,
                "gym_name": gym_name,
                "location": address,
                "city": city,
                "member_id": member_id
            },
            "stats": {
                "total_bookings": total_bookings,
                "active_bookings": active_bookings
            }
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    


#######==============================================================
# adminside===========================================================
#admin login=================================================

@app.route('/admin-login', methods=['POST'])
def admin_login():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')

        # Super admin credentials
        ADMIN_EMAIL = "admin@fitzone.com"
        ADMIN_PASSWORD = "admin123"

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            return jsonify({
                "message": "Admin login successful",
                "next_page": "super_admin_dashboard"
            })

        return jsonify({"error": "Invalid admin credentials"}), 401

    except Exception as e:
        return jsonify({"error": str(e)}), 500

#total gyms registered=======================================================================
@app.route('/admin-total-gyms', methods=['GET'])
def total_gyms():
    cur = mysql.connection.cursor()

    cur.execute("SELECT COUNT(*) FROM gyms")
    count = cur.fetchone()[0]

    cur.close()

    return jsonify({
        "total_gyms": count
    })

#total members across all gyms

@app.route('/admin-total-members', methods=['GET'])
def total_members():
    cur = mysql.connection.cursor()

    cur.execute("SELECT COUNT(*) FROM users WHERE role='gym_user'")
    count = cur.fetchone()[0]

    cur.close()

    return jsonify({
        "total_members": count
    })

#Total bookings across all gyms
@app.route('/admin-total-bookings', methods=['GET'])
def total_bookings():
    cur = mysql.connection.cursor()

    cur.execute("SELECT COUNT(*) FROM bookings")
    count = cur.fetchone()[0]

    cur.close()

    return jsonify({
        "total_bookings": count
    })

#registered gyms list
@app.route('/admin-gyms', methods=['GET'])
def admin_gyms():
    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT g.gym_id, g.gym_name, g.city,
        COUNT(u.user_id) as members
        FROM gyms g
        LEFT JOIN users u ON g.gym_id = u.gym_id
        GROUP BY g.gym_id
    """)

    gyms = cur.fetchall()

    result = []

    for g in gyms:
        result.append({
            "gym_id": g[0],
            "gym_name": g[1],
            "city": g[2],
            "members": g[3],
            "status": "Active"
        })

    cur.close()

    return jsonify(result)

#suspend gym =============================================================
@app.route('/admin-suspend-gym', methods=['POST'])
def suspend_gym():
    data = request.json
    gym_id = data.get("gym_id")

    cur = mysql.connection.cursor()

    cur.execute("""
        UPDATE gyms
        SET status='Suspended'
        WHERE gym_id=%s
    """, (gym_id,))

    mysql.connection.commit()
    cur.close()

    return jsonify({
        "message": "Gym suspended successfully"
    })

# system status 
@app.route('/admin-system-status', methods=['GET'])
def system_status():

    return jsonify({
        "api_status": "Operational",
        "ai_models": "Active",
        "database": "Healthy"
    })

#growth metrics===========================================================================
@app.route('/admin-growth', methods=['GET'])
def growth_metrics():

    return jsonify({
        "gym_growth": "+15%",
        "member_growth": "+22%",
        "booking_growth": "+18%"
    })

###############
@app.route('/admin-activity', methods=['GET'])
def admin_activity():

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT activity, created_at
        FROM system_activity
        ORDER BY created_at DESC
        LIMIT 10
    """)

    logs = cur.fetchall()

    cur.close()

    result = []

    for log in logs:
        result.append({
            "activity": log[0],
            "time": str(log[1])
        })

    return jsonify(result)



if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
