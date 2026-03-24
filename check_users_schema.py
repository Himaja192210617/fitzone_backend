import MySQLdb
try:
    db = MySQLdb.connect(host="localhost", user="root", passwd="", db="gym_fit_zone")
    cur = db.cursor()
    cur.execute("DESC users")
    rows = cur.fetchall()
    print("USERS TABLE SCHEMA:")
    for row in rows:
        print(row)
    db.close()
except Exception as e:
    print(f"ERROR: {e}")
