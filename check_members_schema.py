import MySQLdb
try:
    db = MySQLdb.connect(host="localhost", user="root", passwd="", db="gym_fit_zone")
    cur = db.cursor()
    cur.execute("DESC gym_member_master")
    rows = cur.fetchall()
    print("GYM_MEMBER_MASTER TABLE SCHEMA:")
    for row in rows:
        print(row)
    db.close()
except Exception as e:
    print(f"ERROR: {e}")
