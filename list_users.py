from flask import Flask
from flask_mysqldb import MySQL

app = Flask(__name__)
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'gym_fit_zone'

mysql = MySQL(app)

def list_users():
    with app.app_context():
        cur = mysql.connection.cursor()
        cur.execute("SELECT user_id, email, role, setup_completed FROM users")
        users = cur.fetchall()
        cur.close()
        for u in users:
            print(f"ID: {u[0]}, Email: {u[1]}, Role: {u[2]}, Setup: {u[3]}")

if __name__ == "__main__":
    list_users()
