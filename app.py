from flask import Flask, request, jsonify, send_from_directory
from pathlib import Path
from datetime import datetime, timezone
import sqlite3, os, uuid, json

BASE_DIR = Path(__file__).resolve().parent
# SQLite is suitable for a simple demo. For durable production data, use a managed database.
DB_PATH = Path(os.environ.get("DB_PATH", str(BASE_DIR / "job_applications.db")))
app = Flask(__name__, static_folder=None)

def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS successful_applications(
            candidate_id TEXT PRIMARY KEY, full_name TEXT, email TEXT, phone TEXT,
            position TEXT, experience_years TEXT, location TEXT, availability TEXT,
            source TEXT, status TEXT NOT NULL, submission_id TEXT NOT NULL,
            timestamp_utc TEXT NOT NULL, error_message TEXT NOT NULL DEFAULT '')""")
        c.execute("""CREATE TABLE IF NOT EXISTS submission_attempts(
            attempt_id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT NOT NULL,
            status TEXT NOT NULL, submission_id TEXT NOT NULL DEFAULT '',
            timestamp_utc TEXT NOT NULL, error_message TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL)""")

@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")

@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})

@app.post("/api/submit")
def submit():
    data = request.get_json(silent=True) or {}
    cid = str(data.get("Candidate_ID", "")).strip()
    required = ["Full_Name", "Email", "Phone", "Position", "Experience_Years", "Location", "Availability"]
    if not cid or any(not str(data.get(k, "")).strip() for k in required):
        return jsonify({"status": "FAILED", "message": "Required fields are missing"}), 400

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    payload = json.dumps(data, ensure_ascii=False)
    with db() as c:
        existing = c.execute("SELECT submission_id FROM successful_applications WHERE candidate_id=?", (cid,)).fetchone()
        if existing:
            c.execute("""INSERT INTO submission_attempts(candidate_id,status,submission_id,timestamp_utc,error_message,payload_json)
                          VALUES(?,?,?,?,?,?)""",
                      (cid, "DUPLICATE", existing["submission_id"], ts, "Duplicate Candidate ID", payload))
            return jsonify({"status": "DUPLICATE", "message": "Duplicate Candidate ID"}), 409

        sid = "DEMO-" + uuid.uuid4().hex[:10].upper()
        c.execute("""INSERT INTO successful_applications
          (candidate_id,full_name,email,phone,position,experience_years,location,availability,source,status,submission_id,timestamp_utc,error_message)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (cid, str(data.get("Full_Name", "")), str(data.get("Email", "")), str(data.get("Phone", "")),
           str(data.get("Position", "")), str(data.get("Experience_Years", "")), str(data.get("Location", "")),
           str(data.get("Availability", "")), str(data.get("Source", "")), "SUCCESS", sid, ts, ""))
        c.execute("""INSERT INTO submission_attempts(candidate_id,status,submission_id,timestamp_utc,error_message,payload_json)
                     VALUES(?,?,?,?,?,?)""", (cid, "SUCCESS", sid, ts, "", payload))
    return jsonify({"status": "SUCCESS"}), 200

# Ensure tables are created when started by Gunicorn as well as when run locally.
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
