from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_mysqldb import MySQL
from config import Config
import hashlib
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime, timedelta, date
import os
import random
import traceback

app = Flask(__name__)
CORS(app)

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



# ------------------------------
# Helper Function - Time Formatting
# ------------------------------
def format_to_am_pm(time_str):
    try:
        if not time_str: return "N/A"
        time_obj = datetime.strptime(time_str, "%H:%M")
        return time_obj.strftime("%I:%M %p").lstrip('0')
    except:
        return time_str

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({
        "status": "ok",
        "app": "gym-fitzone",
        "version": "2.0",
        "server_time": str(datetime.now())
    })

@app.errorhandler(500)
def handle_500(e):
    print(f"🔥 GLOBAL 500 ERROR: {str(e)}")
    traceback.print_exc()
    return jsonify({"error": "Internal Server Error", "details": str(e)}), 500

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

        role = data.get('role', 'gym_user').lower().strip()

        if role not in ["gym_user", "gym_administrator", "super_admin"]:
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
            (name, age, gender, email, mobile, password, role, setup_completed, gym_id, reset_token)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            name,
            age,
            gender,
            email,
            mobile,
            password,
            role,
            False,   # setup not completed
            None,    # gym not selected yet
            ''       # empty reset token
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
        gym_id = existing[0]
        # Update existing gym instead of creating a new one
        cur.execute("""
            UPDATE gyms
            SET gym_name=%s, address=%s, location=%s, city=%s, phone=%s, email=%s, description=%s
            WHERE gym_id=%s
        """, (gym_name, address, address, city, phone, email, description, gym_id))
        mysql.connection.commit()
        cur.close()
        return jsonify({
            "message": "Gym details updated",
            "next_step": "configure_hours",
            "gym_id": gym_id
        })

    # Insert gym
    cur.execute("""
        INSERT INTO gyms
        (gym_name, address, location, city, phone, email, description, gym_admin_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (gym_name, address, address, city, phone, email, description, gym_admin_id))

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

        import pandas as pd
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
                    datetime.strptime(str(row['date']), "%Y-%m-%d").date(),
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

        import pandas as pd
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
            SELECT g.gym_id, g.gym_name, g.address, g.city, u.name, g.phone, g.email, g.description 
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
        gym_phone = gym[5]
        gym_email = gym[6]
        gym_description = gym[7]

        # 1️⃣ Total Members
        cur.execute(
            "SELECT COUNT(*) FROM gym_member_master WHERE gym_id=%s",
            (gym_id,)
        )
        total_members = cur.fetchone()[0]

        # 2️⃣ Today's Bookings (Active Only)
        cur.execute("""
            SELECT COUNT(*) FROM bookings
            WHERE gym_id=%s AND DATE(booking_date)=CURDATE() AND booking_status != 'cancelled'
        """, (gym_id,))
        todays_bookings = cur.fetchone()[0]

        # 3️⃣ Total Bookings (Active Only)
        cur.execute(
            "SELECT COUNT(*) FROM bookings WHERE gym_id=%s AND booking_status != 'cancelled'",
            (gym_id,)
        )
        total_bookings = cur.fetchone()[0]

        # 4️⃣ Peak Time (Active Only)
        cur.execute("""
            SELECT time_slot, COUNT(*) as count 
            FROM bookings 
            WHERE gym_id=%s AND booking_status != 'cancelled'
            GROUP BY time_slot 
            ORDER BY count DESC 
            LIMIT 1
        """, (gym_id,))
        peak_row = cur.fetchone()
        peak_time = peak_row[0] if peak_row else "N/A"

        # 5️⃣ Time Slots Count (Total unique hourly slots)
        cur.execute("SELECT open_time, close_time FROM gym_hours WHERE gym_id=%s", (gym_id,))
        operating_sessions = cur.fetchall()
        unique_hours = set()
        for session in operating_sessions:
            open_t, close_t = session[0], session[1]
            if isinstance(open_t, str):
                s_h = int(open_t.split(':')[0])
            else: # timedelta
                s_h = int(open_t.total_seconds() // 3600)
            if isinstance(close_t, str):
                e_h = int(close_t.split(':')[0])
            else: # timedelta
                e_h = int(close_t.total_seconds() // 3600)

            if e_h < s_h:
                unique_hours.update(range(s_h, 24))
                unique_hours.update(range(0, e_h))
            else:
                unique_hours.update(range(s_h, e_h))
        
        time_slots = len(unique_hours)

        # 6️⃣ Popular Workouts (Active Only)
        cur.execute("""
            SELECT workout_type, COUNT(*) as count 
            FROM bookings 
            WHERE gym_id=%s AND booking_status != 'cancelled'
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
                    "count": count,
                    "percentage": percentage
                })

        # 7️⃣ Peak Hours Analysis (Counts by time slot, Active Only)
        cur.execute("""
            SELECT time_slot, COUNT(*) as count 
            FROM bookings 
            WHERE gym_id=%s AND booking_status != 'cancelled'
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
        morning_only_days = [str(row[0]) for row in cur.fetchall()]

        # 🔟 Current Sessions
        cur.execute("SELECT session_type, open_time, close_time FROM gym_hours WHERE gym_id=%s", (gym_id,))
        sessions_rows = cur.fetchall()
        
        def format_td(td):
            if not td: return "00:00"
            if isinstance(td, str): return td[:5]
            total_seconds = int(td.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours:02d}:{minutes:02d}"

        sessions = []
        for s in sessions_rows:
            sessions.append({
                "session_name": s[0],
                "opening_time": format_td(s[1]),
                "closing_time": format_td(s[2])
            })

        cur.close()

        return jsonify({
            "gym_id": gym_id,
            "gym_name": gym_name,
            "location": gym_location,
            "city": gym_city,
            "admin_name": admin_name,
            "phone": gym_phone,
            "email": gym_email,
            "description": gym_description,
            "total_members": total_members,
            "todays_bookings": todays_bookings,
            "total_bookings": total_bookings,
            "time_slots": time_slots,
            "peak_time": peak_time,
            "weekly_growth": "+12%",
            "monthly_growth": "+45%",
            "popular_workouts": popular_workouts,
            "peak_hours": peak_hours,
            "public_holidays": [str(h) for h in public_holidays],
            "morning_only_days": morning_only_days,
            "sessions": sessions
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
                (gym_id, session_type, open_time, close_time)
                VALUES (%s, %s, %s, %s)
            """, (
                gym_id,
                s['session_name'], # Mapping session_name to session_type
                s['opening_time'], # Mapping opening_time to open_time
                s['closing_time']  # Mapping closing_time to close_time
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
@app.route('/remove-holiday', methods=['POST'])
def remove_holiday():
    try:
        data = request.json
        admin_user_id = data.get('admin_user_id')
        holiday_date = data.get('holiday_date')

        cur = mysql.connection.cursor()
        cur.execute("SELECT gym_id FROM gyms WHERE gym_admin_id=%s", (admin_user_id,))
        gym = cur.fetchone()
        if not gym:
            cur.close()
            return jsonify({"error": "Gym not found"}), 404
        
        gym_id = gym[0]
        cur.execute("DELETE FROM gym_holidays WHERE gym_id=%s AND holiday_date=%s", (gym_id, holiday_date))
        mysql.connection.commit()
        cur.close()
        return jsonify({"message": "Holiday removed successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/remove-morning-only', methods=['POST'])
def remove_morning_only():
    try:
        data = request.json
        admin_user_id = data.get('admin_user_id')
        special_date = data.get('special_date')

        cur = mysql.connection.cursor()
        cur.execute("SELECT gym_id FROM gyms WHERE gym_admin_id=%s", (admin_user_id,))
        gym = cur.fetchone()
        if not gym:
            cur.close()
            return jsonify({"error": "Gym not found"}), 404
        
        gym_id = gym[0]
        cur.execute("DELETE FROM morning_only_days WHERE gym_id=%s AND special_date=%s", (gym_id, special_date))
        mysql.connection.commit()
        cur.close()
        return jsonify({"message": "Morning-only day removed successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        
        # 🕒 0️⃣ Auto-expiry: Mark past bookings as 'expired'
        try:
            current_time = datetime.now()
            current_date = current_time.date()
            current_hour_str = current_time.strftime("%H:00")
            
            cur.execute("""
                UPDATE bookings 
                SET booking_status = 'expired' 
                WHERE user_id = %s 
                AND booking_status = 'active'
                AND (booking_date < %s OR (booking_date = %s AND time_slot < %s))
            """, (user_id, current_date, current_date, current_hour_str))
            mysql.connection.commit()
        except Exception as expiry_e:
            print(f"Expiry sync failed in user_home: {str(expiry_e)}")

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

        today = datetime.now().date()

        # 2️⃣ Get dynamic slots & bookings logic
        cur.execute("SELECT slot_capacity FROM gyms WHERE gym_id = %s", (gym_id,))
        capacity_row = cur.fetchone()
        capacity = capacity_row[0] if capacity_row else 10

        cur.execute("SELECT session_type, open_time, close_time FROM gym_hours WHERE gym_id = %s", (gym_id,))
        operating_sessions = cur.fetchall()

        # Check for Morning-Only
        cur.execute("SELECT id FROM morning_only_days WHERE gym_id=%s AND special_date=%s", (gym_id, today))
        is_morning_only = cur.fetchone() is not None

        # Prepare AI
        model_obj = train_gym_model(gym_id)

        allowed_hours = set()
        for session in operating_sessions:
            open_t, close_t = session[1], session[2]
            if isinstance(open_t, str):
                s_h = int(open_t.split(':')[0])
            else: # timedelta
                s_h = int(open_t.total_seconds() // 3600)
            if isinstance(close_t, str):
                e_h = int(close_t.split(':')[0])
            else: # timedelta
                e_h = int(close_t.total_seconds() // 3600)

            if e_h < s_h:
                allowed_hours.update(range(s_h, 24))
                allowed_hours.update(range(0, e_h))
            else:
                allowed_hours.update(range(s_h, e_h))

        slots_info = []
        for hour in sorted(list(allowed_hours)):
            if is_morning_only and hour >= 12:
                continue

            # 🔹 Hide slots that have already passed today
            slot_time = f"{hour:02d}:00"
            if today == datetime.now().date() and hour < datetime.now().hour:
                continue

            cur.execute("""
                SELECT COUNT(*) FROM bookings
                WHERE gym_id=%s AND booking_date=%s AND time_slot=%s AND booking_status='active'
            """, (gym_id, today, slot_time))
            booked = cur.fetchone()[0]
            
            # AI
            predicted = predict_crowd(model_obj, hour, today)
            effective_count = max(booked, predicted)
            
            slots_info.append({
                "time": slot_time,
                "booked": booked,
                "effective": effective_count
            })

        # 2.5 Fetch User's Upcoming Booking for Today
        cur.execute("""
            SELECT time_slot FROM bookings 
            WHERE user_id=%s AND booking_date=%s AND booking_status='active'
            ORDER BY time_slot ASC
        """, (user_id, today))
        booking_row = cur.fetchone()
        user_booking = format_to_am_pm(booking_row[0]) if booking_row else None

        now_hour = datetime.now().hour
        current_percent = 0
        upcoming_peak_percent = 0
        upcoming_peak_time = None
        next_available = None
        
        # Determine global peak for whole day (for analytics/fallback)
        overall_peak_percent = 0
        overall_peak_time = None

        for s in slots_info:
            percent = (s["effective"] / capacity) * 100 if capacity > 0 else 0
            h_int = int(s["time"].split(':')[0])

            # 1. Overall Peak for today
            if percent > overall_peak_percent:
                overall_peak_percent = percent
                overall_peak_time = format_to_am_pm(s["time"])

            # 2. Current Status
            if h_int == now_hour:
                current_percent = percent

            # 3. Next Available (from now onwards)
            if h_int >= now_hour and s["booked"] < capacity and not next_available:
                next_available = format_to_am_pm(s["time"])

            # 4. Upcoming Peak Alert (only slots starting AFTER current hour)
            if h_int > now_hour:
                if percent > upcoming_peak_percent:
                    upcoming_peak_percent = percent
                    upcoming_peak_time = format_to_am_pm(s["time"])

        # Decide current crowd level label
        if current_percent < 40:
            crowd_label = "Low"
        elif current_percent < 75:
            crowd_label = "Medium"
        else:
            crowd_label = "High"

        # Logic for "Real" Peak Alert & Filling Fast Alert
        peak_message = None
        filling_fast_slot = None
        
        # Only show an alert if the upcoming peak is significant (> 70%)
        if upcoming_peak_time and upcoming_peak_percent >= 70:
            peak_message = f"Expected peak crowd at {upcoming_peak_time}"
        elif current_percent >= 80: # If it's peak RIGHT NOW
            peak_message = "Currently experiencing peak hours"

        # Identify Filling Fast Slots (> 85% occupancy)
        for s in slots_info:
            h_int = int(s["time"].split(':')[0])
            if h_int >= now_hour:
                occ_percent = (s["effective"] / capacity) * 100 if capacity > 0 else 0
                if occ_percent >= 85 and s["booked"] < capacity:
                    filling_fast_slot = format_to_am_pm(s["time"])
                    break
        
        # Final Peak Slot for returning (use overall if no upcoming)
        final_peak_slot = upcoming_peak_time if upcoming_peak_time else overall_peak_time

        # 🔹 [NEW] If no more slots available today, find first available tomorrow
        if not next_available:
            try:
                tomorrow_date = today + timedelta(days=1)
                # Check tomorrow's holiday status
                cur.execute("SELECT id FROM gym_holidays WHERE gym_id=%s AND holiday_date=%s", (gym_id, tomorrow_date))
                if not cur.fetchone():
                    # Get tomorrow's first operating hour
                    cur.execute("SELECT open_time FROM gym_hours WHERE gym_id=%s ORDER BY open_time ASC LIMIT 1", (gym_id,))
                    first_op = cur.fetchone()
                    if first_op:
                        op_time = first_op[0]
                        # Robust hour extraction
                        if isinstance(op_time, str):
                            h = int(op_time.split(':')[0])
                        elif hasattr(op_time, 'total_seconds'): # timedelta
                            h = int(op_time.total_seconds() // 3600)
                        else:
                            h = int(str(op_time).split(':')[0])
                        
                        # Check if morning-only tomorrow affects this first slot
                        cur.execute("SELECT id FROM morning_only_days WHERE gym_id=%s AND special_date=%s", (gym_id, tomorrow_date))
                        is_morn = cur.fetchone() is not None
                        
                        if not (is_morn and h >= 12):
                            next_available = f"Tomorrow {format_to_am_pm(f'{h:02d}:00')}"
            except Exception as e:
                print(f"Error fetching tomorrow's slot: {e}")

        # Final safety check
        if not next_available:
             next_available = "Today Full / Closed"

        cur.close()

        def fmt_time(t):
            if not t: return None
            if isinstance(t, str): return t
            # If it's a timedelta (MySQL TIME column usually)
            if hasattr(t, 'seconds') and not hasattr(t, 'hour'):
                return (datetime.min + t).strftime('%H:%M')
            # If it's a native time object
            if hasattr(t, 'hour'):
                return t.strftime('%H:%M')
            return str(t)[:5]


        return jsonify({
            "user_name": str(name),
            "gym_name": str(gym_name),
            "current_crowd_level": crowd_label,
            "next_available_slot": fmt_time(next_available),
            "your_booking": fmt_time(booking_row[0]) if booking_row else None,
            "peak_slot": fmt_time(final_peak_slot) if final_peak_slot else "N/A",
            "peak_message": peak_message,
            "filling_fast_slot": fmt_time(filling_fast_slot)
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

        # 🔹 Generate unique slots based on operating hours
        allowed_hours = set()
        for session in operating_sessions:
            open_t = session[1]
            close_t = session[2]
            
            # Convert to hours
            if isinstance(open_t, str):
                s_h = int(open_t.split(':')[0])
            else: # timedelta
                s_h = int(open_t.total_seconds() // 3600)
                
            if isinstance(close_t, str):
                e_h = int(close_t.split(':')[0])
            else: # timedelta
                e_h = int(close_t.total_seconds() // 3600)
            
            if e_h < s_h: # Midnight crossover
                allowed_hours.update(range(s_h, 24))
                allowed_hours.update(range(0, e_h))
            else:
                allowed_hours.update(range(s_h, e_h))

        # 🔹 AI Integration: Pre-train model for efficiency
        model_obj = train_gym_model(gym_id)
        
        # Pre-calculate hour to session end minutes mapping for dynamic duration limit
        hour_to_session_end = {}
        for session in operating_sessions:
            open_t, close_t = session[1], session[2]
            
            def get_h_m(t):
                if isinstance(t, str):
                    parts = t.split(':')
                    return int(parts[0]), int(parts[1])
                else: # timedelta
                    ts = int(t.total_seconds())
                    return ts // 3600, (ts % 3600) // 60

            sh, sm = get_h_m(open_t)
            eh, em = get_h_m(close_t)
            total_end_min = eh * 60 + em
            
            if eh < sh: # crossover
                for h in range(sh, 24): hour_to_session_end[h] = 1440 # Limit to end of day if crossover
                for h in range(0, eh): hour_to_session_end[h] = total_end_min
            else:
                for h in range(sh, eh): hour_to_session_end[h] = total_end_min

        response = []
        now = datetime.now()
        for hour in sorted(list(allowed_hours)):
            slot_time = f"{hour:02d}:00"

            # 🔹 Respect morning-only logic: skip afternoon/evening slots
            if is_morning_only and hour >= 12:
                continue

            # 🔹 Hide slots that have already passed today
            if selected_date == str(now.date()) and hour < now.hour:
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
            
            # 🔹 Get AI prediction using pre-trained model/logic
            predicted = predict_crowd(model_obj, hour, selected_date)
            effective_count = max(booked, predicted)
            
            # 🔹 Color Code Logic Based on Capacity
            percentage = (effective_count / capacity) * 100 if capacity > 0 else 0
            if percentage < 50:
                color = "green"
                status = "Available"
            elif percentage < 85:
                color = "yellow"
                status = "Filling Fast"
            else:
                color = "red"
                status = "Almost Full"

            if effective_count >= capacity:
                status = "Full"
                color = "red"

            # 🔹 Get specific session boundary for this slot
            session_end_min = hour_to_session_end.get(hour, (hour + 1) * 60) # Default to 1 hour if not found

            response.append({
                "slot": slot_time,
                "booked": booked,
                "capacity": capacity,
                "color": color,
                "status": status,
                "predicted": predicted,
                "session_end_minutes": session_end_min
            })

        # Sort slots by time
        response.sort(key=lambda x: x['slot'])

        cur.close()
        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    # ==========================================================================
# Helper for hour extraction (handles "06:00", "6 PM - 8 PM", "10-12 AM", "06:00-08:00")
def get_hours_list(s):
    try:
        if not s: return []
        import re
        s = str(s).upper().replace(' ', '')
        # Split by common range separators
        blocks = re.split(r'[-–—TO]', s)
        hours = []
        for b in blocks:
            if not b: continue
            # Match the first number in the block (treating it as the hour)
            m = re.search(r'(\d+)', b)
            if m:
                h = int(m.group(1))
                # Check for AM/PM context in the block
                if 'PM' in b and h < 12: h += 12
                if 'AM' in b and h == 12: h = 0
                hours.append(h)
        
        if len(hours) >= 2:
            start, end = hours[0], hours[1]
            if end < start and end < 12: end += 12
            if start == end: return [start]
            return list(range(start, end))
        elif len(hours) == 1:
            return [hours[0]]
        return []
    except:
        return []

def train_gym_model(gym_id):
    try:
        import pandas as pd
        from sklearn.ensemble import RandomForestRegressor
        import re

        cur = mysql.connection.cursor()
        # 1️⃣ Get Historical Data
        cur.execute("SELECT booking_date, slot, booking_count FROM historical_bookings WHERE gym_id = %s", (gym_id,))
        hist = cur.fetchall()
        
        # 2️⃣ Get Current Booking Data
        cur.execute("""
            SELECT booking_date, time_slot, COUNT(*) 
            FROM bookings 
            WHERE gym_id = %s AND booking_status = 'active'
            GROUP BY booking_date, time_slot
        """, (gym_id,))
        curr = cur.fetchall()
        cur.close()

        if not hist and not curr:
            return None

        # Prepare dataset
        records = []
        for d, s, c in hist:
            try:
                hours = get_hours_list(s)
                day = d.weekday() if hasattr(d, 'weekday') else 0
                month = d.month if hasattr(d, 'month') else 1
                for h in hours:
                    records.append({'day': day, 'month': month, 'hour': h, 'count': int(c)})
            except: continue
            
        for d, s, c in curr:
            try:
                hours = get_hours_list(s)
                day = d.weekday() if hasattr(d, 'weekday') else 0
                month = d.month if hasattr(d, 'month') else 1
                for h in hours:
                    records.append({'day': day, 'month': month, 'hour': h, 'count': int(c)})
            except: continue

        if not records:
            return None

        df = pd.DataFrame(records)
        df['is_weekend'] = df['day'].apply(lambda x: 1 if x >= 5 else 0)
        
        # Training
        if len(df) >= 5:
            X = df[['day', 'month', 'hour', 'is_weekend']]
            y = df['count']
            model = RandomForestRegressor(n_estimators=10, random_state=42)
            model.fit(X, y)
            return {"model": model, "df": df, "use_model": True}
        else:
            return {"df": df, "use_model": False}

    except Exception as e:
        print(f"AI Training Error: {str(e)}")
        return None

def predict_crowd(model_obj, hour_val, target_date=None):
    if not model_obj:
        return 0
    try:
        if target_date is None:
            now = datetime.now()
        elif isinstance(target_date, str):
            try:
                now = datetime.strptime(target_date, "%Y-%m-%d")
            except:
                now = datetime.now()
        else:
            now = target_date # Assume it's a date or datetime object

        target_day = now.weekday()
        target_month = now.month
        target_weekend = 1 if target_day >= 5 else 0

        if model_obj.get("use_model") and model_obj.get("model"):
            pred = model_obj["model"].predict([[target_day, target_month, hour_val, target_weekend]])
            return int(round(pred[0]))
        else:
            df = model_obj.get("df")
            if df is not None and not df.empty:
                filtered = df[df['hour'] == hour_val]
                if not filtered.empty:
                    return int(round(filtered['count'].mean()))
            return 0
    except Exception as e:
        print(f"AI Prediction Error: {str(e)}")
        return 0

def train_model(gym_id, slot_time, target_date=None):
    # Compatibility wrapper
    obj = train_gym_model(gym_id)
    hours = get_hours_list(slot_time)
    h = hours[0] if hours else 0
    return predict_crowd(obj, h, target_date)

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
        predicted = train_model(gym_id, slot_time, selected_date)

        # 5️⃣ Trend logic
        if predicted > total_bookings:
            trend = "Crowd expected to increase."
        elif predicted == total_bookings:
            trend = "Stable trend."
        else:
            trend = "Less crowded than usual."

        # 6️⃣ Log AI prediction vs actual
        try:
            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO ai_prediction_logs
                (gym_id, slot, predicted_count, actual_count, prediction_date)
                VALUES (%s,%s,%s,%s,%s)
            """, (gym_id, slot_time, predicted, total_bookings, selected_date))
            mysql.connection.commit()
            cur.close()
        except Exception as log_error:
            print(f"Log Error: {log_error}")

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
        try:
            selected_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
            today = datetime.now().date()
        except Exception as e:
            return jsonify({"error": f"Invalid date format: {str(e)}"}), 400

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

        # 🔒 Check if duration exceeds session closing time
        cur.execute("SELECT open_time, close_time FROM gym_hours WHERE gym_id=%s", (gym_id,))
        sessions = cur.fetchall()
        
        try:
            sh_req, sm_req = map(int, time_slot.split(':'))
            start_total_req = sh_req * 60 + sm_req
            end_total_req = start_total_req + duration
            
            # Helper to get minutes from session time
            def get_m(t):
               if isinstance(t, str):
                   h, m = map(int, t.split(':')[:2])
                   return h * 60 + m
               ts = int(t.total_seconds())
               return (ts // 3600) * 60 + ((ts % 3600) // 60)

            valid_session = False
            session_ending = 1440
            for s_open, s_close in sessions:
                s_sh = get_m(s_open)
                s_eh = get_m(s_close)
                
                if s_eh < s_sh: # crossover
                    if start_total_req >= s_sh or start_total_req < s_eh:
                        valid_session = True
                        session_ending = s_eh if start_total_req < s_eh else 1440
                        break
                else:
                    if s_sh <= start_total_req < s_eh:
                        valid_session = True
                        session_ending = s_eh
                        break
            
            if valid_session and end_total_req > session_ending:
                cur.close()
                return jsonify({"error": f"Booking duration exceeds session closing time ({session_ending // 60}:{session_ending % 60:02d})."}), 400
        except Exception as e:
            pass # fallback if time parsing fails

        # 🔒 Prevent multiple bookings on the same day (1 per day rule)
        cur.execute("""
            SELECT booking_id, time_slot
            FROM bookings
            WHERE user_id=%s
            AND booking_date=%s
            AND booking_status='active'
        """, (user_id, booking_date))
        
        existing_any = cur.fetchone()
        if existing_any:
            cur.close()
            return jsonify({
                "error": f"You already have a booking for today at {existing_any[1]}. Only 1 booking per day is allowed."
            }), 400

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
            selected_date.strftime("%A"),
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
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

#== History=======================================================================
@app.route('/history/<int:user_id>', methods=['GET'])
def history(user_id):
    try:
        print(f"DEBUG: Fetching history for user_id: {user_id}")
        cur = mysql.connection.cursor()

        # 🕒 0️⃣ Auto-expiry: Mark passed slots as 'expired'
        try:
            current_time = datetime.now()
            current_date = current_time.date()
            current_hour_str = current_time.strftime("%H:00")
            
            cur.execute("""
                UPDATE bookings 
                SET booking_status = 'expired' 
                WHERE user_id = %s 
                AND booking_status = 'active'
                AND (booking_date < %s OR (booking_date = %s AND time_slot < %s))
            """, (user_id, current_date, current_date, current_hour_str))
            mysql.connection.commit()
        except Exception as expiry_e:
            print(f"Expiry sync failed: {str(expiry_e)}")
            traceback.print_exc()

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
            ORDER BY (booking_status = 'active') DESC, booking_date DESC, time_slot DESC
        """, (user_id,))

        rows = cur.fetchall()
        print(f"DEBUG: Found {len(rows)} history items for user {user_id}")
        cur.close()

        result = []
        today = date.today()

        for row in rows:
            booking_id = row[0]
            booking_date = row[1]
            time_slot = row[2]
            summary = row[3]           # Cardio + Chest + Tricep
            details = row[4]           # Chest - Bench Press...
            duration = row[5]
            status = row[6]

            # Optional: Cancel allowed only for future bookings
            cancel_allowed = False
            if booking_date and status == "active":
                try:
                    # Convert to datetime.date object regardless of input type
                    if isinstance(booking_date, str):
                        b_date = datetime.strptime(booking_date.split(' ')[0], "%Y-%m-%d").date()
                    elif hasattr(booking_date, 'date'): # if it's a datetime object
                        b_date = booking_date.date()
                    else: # it's already a date object
                        b_date = booking_date
                    
                    if b_date >= today:
                        cancel_allowed = True
                except Exception as de:
                    print(f"Date conversion error: {str(de)}")
                    pass

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
        traceback.print_exc()
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



# Super Admin Dashboard Data Layer
@app.route('/super-admin-dashboard', methods=['GET'])
def super_admin_dashboard():
    try:
        cur = mysql.connection.cursor()
        
        # 1. Total Gyms
        cur.execute("SELECT COUNT(*) FROM gyms")
        total_gyms = cur.fetchone()[0]
        
        # 2. Total Members
        cur.execute("SELECT COUNT(*) FROM users WHERE role='gym_user'")
        total_members = cur.fetchone()[0]
        
        # 3. Total Bookings (Active Only)
        cur.execute("SELECT COUNT(*) FROM bookings WHERE booking_status != 'cancelled'")
        total_bookings = cur.fetchone()[0]
        
        # 4. Registered Gyms List
        cur.execute("""
            SELECT g.gym_id, g.gym_name, g.city, 
                   (SELECT COUNT(*) FROM users u WHERE u.gym_id = g.gym_id) as member_count
            FROM gyms g
        """)
        gyms_data = cur.fetchall()
        
        gyms_list = []
        for g in gyms_data:
            gyms_list.append({
                "gym_id": g[0],
                "gym_name": g[1],
                "city": g[2],
                "status": "Active", 
                "members": g[3]
            })

        # 5. Activity Logs (Real bookings history)
        cur.execute("""
            SELECT b.booking_date, u.name, g.gym_name
            FROM bookings b
            JOIN users u ON b.user_id = u.user_id
            JOIN gyms g ON b.gym_id = g.gym_id
            ORDER BY b.booking_id DESC LIMIT 8
        """)
        recent_activity = cur.fetchall()
        activity_logs = []
        for act in recent_activity:
            activity_logs.append({
                "activity": f"{act[1]} registered a booking at {act[2]}",
                "time": str(act[0])
            })
            
        cur.close()
        
        return jsonify({
            "totalGyms": total_gyms,
            "totalMembers": total_members,
            "totalBookings": total_bookings,
            "status": { "api_status": "Online", "ai_models": "Active", "database": "Connected" },
            "growth": { "gym_growth": "+5%", "member_growth": "+12%", "booking_growth": "+18%" },
            "activity": activity_logs,
            "gyms": gyms_list
        })
        
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
        password_input = data['password']
        hashed_password = hash_password(password_input)

        # 🛡️ HARDCODED SUPER ADMIN BYPASS
        if email == "admin@fitzone.com" and password_input == "admin123":
            return jsonify({
                "message": "Login successful",
                "user_id": 0,
                "role": "super_admin",
                "next_page": "super_admin_dashboard",
                "name": "Super Admin",
                "email": "admin@fitzone.com",
                "gym_id": None
            })

        # Regular users login logic
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT user_id, role, gym_id, setup_completed, name, email, mobile, age, gender, member_id
            FROM users
            WHERE (email=%s OR mobile=%s) AND password=%s
        """, (email, email, hashed_password))

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

        # 🔥 ROLE NORMALIZATION
        role_key = role.lower().strip() if role else ""

        # 🔥 ADMIN FLOW
        if role_key == "gym_administrator":
            if not setup_completed:
                # Determine which step the admin is on
                if not gym_id:
                    next_page = "setup_gym"
                else:
                    cur = mysql.connection.cursor()
                    
                    # 1. Check if hours are configured
                    cur.execute("SELECT COUNT(*) FROM gym_hours WHERE gym_id=%s", (gym_id,))
                    hours_count = cur.fetchone()[0]
                    
                    # 2. Check if members have been uploaded
                    cur.execute("SELECT COUNT(*) FROM gym_member_master WHERE gym_id=%s", (gym_id,))
                    members_count = cur.fetchone()[0]
                    
                    cur.close()
                    
                    if hours_count == 0:
                        next_page = "configure_hours"
                    elif members_count == 0:
                        next_page = "upload_data"
                    else:
                        next_page = "set_capacity"
            else:
                next_page = "gym_dashboard"

        # 🔥 GYM USER FLOW
        elif role_key == "gym_user":
            if not setup_completed:
                next_page = "select_gym"
            else:
                next_page = "user_dashboard"

        # 🔥 SUPER ADMIN FLOW
        elif role_key in ["super_admin", "super admin", "master administrator"]:
            next_page = "super_admin_dashboard"



        else:
            next_page = "login" # Fallback

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
        print(f"DEBUG: Fetching profile for user_id: {user_id}")
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
        print(f"DEBUG: Raw DB User Row for ID {user_id}: {user}")

        if not user:
            return jsonify({"error": "User not found"}), 404

        name, email, mobile, age, gender, member_id, gym_id, role, gym_name, address, city = user

        print(f"DEBUG: User details - Name: {name}, Email: {email}, Mobile: {mobile}, Age: {age}, Gender: {gender}")
        print(f"DEBUG: Gym details - ID: {gym_id}, Name: {gym_name}, MemberID: {member_id}")

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
        try:
            current_time = datetime.now()
            current_date = current_time.date()
            current_hour_str = current_time.strftime("%H:00")
            
            cur.execute("""
                UPDATE bookings 
                SET booking_status = 'expired' 
                WHERE user_id = %s 
                AND booking_status = 'active'
                AND (booking_date < %s OR (booking_date = %s AND time_slot < %s))
            """, (user_id, current_date, current_date, current_hour_str))
            mysql.connection.commit()
        except Exception as expiry_e:
            print(f"Expiry sync failed: {str(expiry_e)}")
            traceback.print_exc()

        # 2️⃣ Total bookings (excluding cancelled)
        cur.execute("""
            SELECT COUNT(*)
            FROM bookings
            WHERE user_id=%s AND booking_status != 'cancelled'
        """, (user_id,))
        total_bookings_res = cur.fetchone()
        total_bookings = total_bookings_res[0] if total_bookings_res else 0
        print(f"DEBUG: Total Bookings for user {user_id}: {total_bookings}")

        # 3️⃣ Active bookings (future/today bookings that are NOT cancelled)
        cur.execute("""
            SELECT COUNT(*)
            FROM bookings
            WHERE user_id=%s
            AND booking_date >= CURDATE()
            AND booking_status = 'active'
        """, (user_id,))
        active_bookings_res = cur.fetchone()
        active_bookings = active_bookings_res[0] if active_bookings_res else 0
        print(f"DEBUG: Active Bookings for user {user_id}: {active_bookings}")

        cur.close()

        # Helper to safely convert to int
        def safe_int(val, default=0):
            try:
                if val is None: return default
                return int(val)
            except:
                return default

        resp = {
            "name": str(name) if name is not None else "Guest",
            "role": str(role) if role is not None else "user",
            "email": str(email) if email is not None else "N/A",
            "mobile": str(mobile) if mobile is not None else "N/A",
            "age": safe_int(age),
            "gender": str(gender) if gender is not None else "N/A",
            "gym": {
                "gym_id": safe_int(gym_id),
                "gym_name": str(gym_name) if gym_name is not None else "Not Selected",
                "location": str(address) if address is not None else "N/A",
                "city": str(city) if city is not None else "N/A",
                "member_id": str(member_id) if member_id is not None else "N/A"
            },
            "stats": {
                "total_bookings": safe_int(total_bookings),
                "active_bookings": safe_int(active_bookings)
            }
        }
        print(f"DEBUG: Returning profile: {resp}")
        return jsonify(resp)

    except Exception as e:
        print(f"ERROR in user_profile: {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/update-profile', methods=['POST'])
def update_profile():
    try:
        data = request.json
        user_id = data.get('user_id')
        name = data.get('name')
        email = data.get('email')
        mobile = data.get('mobile')
        age = data.get('age')
        gender = data.get('gender')

        print(f"DEBUG: Update requested for user_id: {user_id}")

        if not user_id:
            return jsonify({"message": "user_id is required"}), 400

        cur = mysql.connection.cursor()
        
        # Build update query dynamically
        fields = []
        values = []
        if name: fields.append("name=%s"); values.append(name)
        if email: fields.append("email=%s"); values.append(email)
        if mobile: fields.append("mobile=%s"); values.append(mobile)
        if age is not None: fields.append("age=%s"); values.append(age)
        if gender: fields.append("gender=%s"); values.append(gender)

        if not fields:
             cur.close()
             return jsonify({"message": "No fields to update"}), 400

        sql = f"UPDATE users SET {', '.join(fields)} WHERE user_id=%s"
        values.append(user_id)
        
        print(f"DEBUG: SQL: {sql} with values {values}")
        
        cur.execute(sql, tuple(values))
        mysql.connection.commit()
        cur.close()

        return jsonify({"message": "Profile updated successfully"})
    except Exception as e:
        print(f"ERROR in update_profile: {str(e)}")
        traceback.print_exc()
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

    cur.execute("SELECT COUNT(*) FROM bookings WHERE booking_status != 'cancelled'")
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
    try:
        cur = mysql.connection.cursor()
        
        # 1. Gym Growth (Current month vs Previous)
        cur.execute("SELECT COUNT(*) FROM gyms WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)")
        this_month_gyms = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM gyms WHERE created_at < DATE_SUB(NOW(), INTERVAL 1 MONTH) AND created_at >= DATE_SUB(NOW(), INTERVAL 2 MONTH)")
        last_month_gyms = cur.fetchone()[0]
        
        gym_growth = ((this_month_gyms - last_month_gyms) / last_month_gyms * 100) if last_month_gyms > 0 else (this_month_gyms * 100)
        
        # 2. Member Growth
        cur.execute("SELECT COUNT(*) FROM users WHERE role='gym_user' AND created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)")
        this_month_members = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE role='gym_user' AND created_at < DATE_SUB(NOW(), INTERVAL 1 MONTH) AND created_at >= DATE_SUB(NOW(), INTERVAL 2 MONTH)")
        last_month_members = cur.fetchone()[0]
        
        member_growth = ((this_month_members - last_month_members) / last_month_members * 100) if last_month_members > 0 else (this_month_members * 100)
        
        # 3. Booking Growth
        cur.execute("SELECT COUNT(*) FROM bookings WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)")
        this_month_bookings = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM bookings WHERE created_at < DATE_SUB(NOW(), INTERVAL 1 MONTH) AND created_at >= DATE_SUB(NOW(), INTERVAL 2 MONTH)")
        last_month_bookings = cur.fetchone()[0]
        
        booking_growth = ((this_month_bookings - last_month_bookings) / last_month_bookings * 100) if last_month_bookings > 0 else (this_month_bookings * 100)
        
        cur.close()
        
        return jsonify({
            "gym_growth": f"{'+' if gym_growth >= 0 else ''}{int(gym_growth)}%",
            "member_growth": f"{'+' if member_growth >= 0 else ''}{int(member_growth)}%",
            "booking_growth": f"{'+' if booking_growth >= 0 else ''}{int(booking_growth)}%"
        })
    except Exception as e:
        return jsonify({"gym_growth": "+0%", "member_growth": "+0%", "booking_growth": "+0%"})

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
