import MySQLdb
try:
    db = MySQLdb.connect(host="localhost", user="root", passwd="", db="gym_fit_zone")
    cur = db.cursor()
    cur.execute("SELECT user_id, name, email, role, setup_completed, gym_id FROM users")
    users = cur.fetchall()
    print("USERS:")
    for u in users:
        print(u)
    
    cur.execute("SELECT * FROM gyms")
    gyms = cur.fetchall()
    print("\nGYMS:")
    for g in gyms:
        print(g)
    db.close()
except Exception as e:
    print(f"ERROR: {e}")
