from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
import cv2
import numpy as np
import base64
import sqlite3
import datetime

app = Flask(__name__)
app.secret_key = "supersecretkey"

current_session_id = None

# ---------------- DATABASE SETUP ----------------

def init_db():
    conn = sqlite3.connect("driver_data.db")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            start_time TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            status TEXT,
            timestamp TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ---------------- AUTH ----------------

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    password = request.form["password"]

    conn = sqlite3.connect("driver_data.db")
    c = conn.cursor()

    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
    except:
        return "User already exists"

    conn.close()
    return redirect(url_for("home"))

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    conn = sqlite3.connect("driver_data.db")
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    user = c.fetchone()
    conn.close()

    if user:
        session["user_id"] = user[0]
        return redirect(url_for("dashboard"))
    else:
        return "Invalid credentials"

# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("home"))
    return render_template("dashboard.html")

@app.route("/start-session", methods=["POST"])
def start_session():
    global current_session_id

    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401

    user_id = session["user_id"]

    conn = sqlite3.connect("driver_data.db")
    c = conn.cursor()

    start_time = str(datetime.datetime.now())
    c.execute("INSERT INTO sessions (user_id, start_time) VALUES (?, ?)", (user_id, start_time))
    current_session_id = c.lastrowid

    conn.commit()
    conn.close()

    return jsonify({"session_id": current_session_id})

@app.route("/analyze", methods=["POST"])
def analyze():
    global current_session_id

    if current_session_id is None:
        return jsonify({"error": "Start session first"}), 400

    data = request.json["image"]

    image_data = base64.b64decode(data.split(",")[1])
    np_arr = np.frombuffer(image_data, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    status = "SAFE"
    if len(faces) == 0:
        status = "DROWSY"

    conn = sqlite3.connect("driver_data.db")
    c = conn.cursor()

    c.execute(
        "INSERT INTO events (session_id, status, timestamp) VALUES (?, ?, ?)",
        (current_session_id, status, str(datetime.datetime.now()))
    )

    conn.commit()
    conn.close()

    return jsonify({"status": status})

@app.route("/summary")
def summary():
    global current_session_id

    if current_session_id is None:
        return jsonify({"message": "No active session"})

    conn = sqlite3.connect("driver_data.db")
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM events WHERE session_id=?", (current_session_id,))
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM events WHERE session_id=? AND status='DROWSY'", (current_session_id,))
    drowsy = c.fetchone()[0]

    conn.close()

    safety_score = round((1 - (drowsy/total)) * 100, 2) if total > 0 else 100

    return jsonify({
        "session_id": current_session_id,
        "total_checks": total,
        "drowsy_events": drowsy,
        "safety_score": safety_score
    })

# ---------------- REPORTS ----------------

@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("home"))

    user_id = session["user_id"]

    conn = sqlite3.connect("driver_data.db")
    c = conn.cursor()

    c.execute("SELECT id, start_time FROM sessions WHERE user_id=? ORDER BY id DESC", (user_id,))
    sessions = c.fetchall()

    conn.close()

    return render_template("history.html", sessions=sessions)

@app.route("/report/<int:session_id>")
def report(session_id):
    conn = sqlite3.connect("driver_data.db")
    c = conn.cursor()

    c.execute("SELECT start_time FROM sessions WHERE id=?", (session_id,))
    session_data = c.fetchone()

    if not session_data:
        return "Session not found"

    start_time = session_data[0]

    c.execute("SELECT COUNT(*) FROM events WHERE session_id=?", (session_id,))
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM events WHERE session_id=? AND status='DROWSY'", (session_id,))
    drowsy = c.fetchone()[0]

    conn.close()

    safety_score = round((1 - (drowsy/total)) * 100, 2) if total > 0 else 100

    if safety_score > 85:
        risk = "LOW RISK"
    elif safety_score > 60:
        risk = "MODERATE RISK"
    else:
        risk = "HIGH RISK"

    return render_template(
        "report.html",
        session_id=session_id,
        start_time=start_time,
        total=total,
        drowsy=drowsy,
        safety_score=safety_score,
        risk=risk
    )

@app.route("/download/<int:session_id>")
def download(session_id):

    conn = sqlite3.connect("driver_data.db")
    c = conn.cursor()

    c.execute("SELECT status, timestamp FROM events WHERE session_id=?", (session_id,))
    rows = c.fetchall()

    conn.close()

    def generate():
        yield "Status,Timestamp\n"
        for row in rows:
            yield f"{row[0]},{row[1]}\n"

    return Response(generate(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment;filename=session_{session_id}.csv"})

if __name__ == "__main__":
    app.run(threaded=True)