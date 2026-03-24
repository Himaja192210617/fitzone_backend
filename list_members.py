import MySQLdb
try:
    db = MySQLdb.connect(host="localhost", user="root", passwd="", db="gym_fit_zone")
    cur = db.cursor()
    cur.execute("SELECT member_id, name FROM gym_member_master")
    members = cur.fetchall()
    print("MEMBERS:")
    for m in members:
        print(m)
    db.close()
except Exception as e:
    print(f"ERROR: {e}")
