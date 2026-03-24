import mysql.connector
from config import Config

def check_gym_hours():
    try:
        conn = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB
        )
        cur = conn.cursor()
        
        # Get all gyms
        cur.execute("SELECT gym_id, gym_name FROM gyms")
        gyms = cur.fetchall()
        
        print("--- Gym Hours Debug ---")
        for g_id, g_name in gyms:
            print(f"\nGym: {g_name} (ID: {g_id})")
            cur.execute("SELECT session_type, open_time, close_time FROM gym_hours WHERE gym_id = %s", (g_id,))
            hours = cur.fetchall()
            if not hours:
                print("  No hours configured.")
            for session, open_t, close_t in hours:
                print(f"  Session: {session}, Open: {open_t}, Close: {close_t}")
            
            cur.execute("SELECT slot_capacity FROM gyms WHERE gym_id = %s", (g_id,))
            cap = cur.fetchone()
            print(f"  Capacity: {cap[0] if cap else 'N/A'}")

        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_gym_hours()
