import os
import sqlite3
import secrets
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "site.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

login_manager = LoginManager(app)
login_manager.login_view = "login"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            is_verified INTEGER NOT NULL DEFAULT 0,
            verify_token TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS download_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            filename TEXT NOT NULL,
            downloaded_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_db()

MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")


def send_verification_email(to_email, token):
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("[WARN] MAIL_USERNAME/MAIL_PASSWORDが未設定のためメール送信スキップ")
        return

    verify_url = f"{BASE_URL}/verify/{token}"
    body = f"以下のリンクをクリックしてアカウントを有効化してください:\n\n{verify_url}"
    msg = MIMEText(body)
    msg["Subject"] = "【配布サイト】メール認証のお願い"
    msg["From"] = MAIL_USERNAME
    msg["To"] = to_email

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(msg)

ADMIN_USERNAMES = {"kensinmukaedao@gmail.com"}

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row:
        return User(row["id"], row["username"])
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        email = request.form.get("email", "").strip()

        if not username or not password or not email:
            flash("ユーザー名・メールアドレス・パスワードを入力してください")
            return redirect(url_for("register"))
        if len(password) < 8:
            flash("パスワードは8文字以上にしてください")
            return redirect(url_for("register"))

        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            flash("そのユーザー名は既に使われています")
            conn.close()
            return redirect(url_for("register"))

        pw_hash = generate_password_hash(password)
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO users (username, password_hash, email, is_verified, verify_token) VALUES (?, ?, ?, 0, ?)",
            (username, pw_hash, email, token),
        )
        conn.commit()
        conn.close()

        send_verification_email(email, token)
        flash("登録が完了しました。届いたメールのリンクから認証してください")
        return redirect(url_for("login"))

    return render_template("register.html")



@app.route("/verify/<token>")
def verify(token):
    conn = get_db()
    row = conn.execute("SELECT id FROM users WHERE verify_token = ?", (token,)).fetchone()
    if row:
        conn.execute("UPDATE users SET is_verified = 1, verify_token = NULL WHERE id = ?", (row["id"],))
        conn.commit()
        conn.close()
        flash("メール認証が完了しました。ログインできます")
    else:
        conn.close()
        flash("無効な認証リンクです")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()

        if row and check_password_hash(row["password_hash"], password):
            if not row["is_verified"]:
                flash("メール認証が完了していません。届いたメールを確認してください")
                return redirect(url_for("login"))
            user = User(row["id"], row["username"])
            login_user(user)
            return redirect(url_for("downloads"))

        flash("ユーザー名またはパスワードが違います")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/downloads")
@login_required
def downloads():
    files = []
    if os.path.isdir(UPLOAD_DIR):
        files = sorted(os.listdir(UPLOAD_DIR))
    return render_template("downloads.html", files=files, username=current_user.username)


@app.route("/downloads/<path:filename>")
@login_required
def download_file(filename):
    try:
        response = send_from_directory(UPLOAD_DIR, filename, as_attachment=True)
    except FileNotFoundError:
        abort(404)

    conn = get_db()
    conn.execute(
        "INSERT INTO download_logs (username, filename, downloaded_at) VALUES (?, ?, ?)",
        (current_user.username, filename, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()

    return response


@app.route("/admin/logs")
@login_required
def admin_logs():
    if current_user.username not in ADMIN_USERNAMES:
        abort(403)

    conn = get_db()
    rows = conn.execute(
        "SELECT username, filename, downloaded_at FROM download_logs ORDER BY downloaded_at DESC"
    ).fetchall()
    conn.close()
    return render_template("admin_logs.html", logs=rows)


@app.route("/admin/users")
@login_required
def admin_users():
    if current_user.username not in ADMIN_USERNAMES:
        abort(403)

    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, password_hash FROM users ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return render_template("admin_users.html", users=rows)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)