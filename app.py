"""安飞智能科技 - 知识库系统 (Knowledge Base)"""
import sqlite3
import os
from datetime import datetime

from flask import (
    Flask, g, render_template, request, redirect,
    session, url_for, abort,
)
import markdown

app = Flask(__name__)
app.secret_key = "wiki-227578-secret-key-anfei-2026"
DB_PATH = os.path.join(os.path.dirname(__file__), "wiki.db")
PASSWORD = "227578"
SITE_NAME = "安飞智能科技 · 知识库"


# ── Database helpers ────────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        db.execute(
            """CREATE TABLE IF NOT EXISTS pages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT UNIQUE NOT NULL,
                content     TEXT NOT NULL DEFAULT '',
                updated_at  TEXT NOT NULL
            )"""
        )
        db.commit()


# ── Auth decorator ──────────────────────────────────────────────────

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


# ── Routes ──────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = "密码错误"
    return render_template("login.html", error=error, site_name=SITE_NAME)


@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    db = get_db()
    pages = db.execute(
        "SELECT title, updated_at FROM pages ORDER BY updated_at DESC"
    ).fetchall()
    return render_template("index.html", pages=pages, site_name=SITE_NAME)


@app.route("/<path:title>")
@login_required
def view_page(title):
    db = get_db()
    row = db.execute(
        "SELECT title, content, updated_at FROM pages WHERE title = ?",
        (title,),
    ).fetchone()
    if row is None:
        abort(404)
    html = markdown.markdown(row["content"], extensions=["fenced_code", "codehilite"])
    return render_template(
        "view.html",
        page=row,
        html=html,
        site_name=SITE_NAME,
    )


@app.route("/<path:title>/edit", methods=["GET", "POST"])
@login_required
def edit_page(title):
    db = get_db()
    row = db.execute(
        "SELECT title, content FROM pages WHERE title = ?", (title,)
    ).fetchone()

    if request.method == "POST":
        new_content = request.form.get("content", "")
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        if row:
            db.execute(
                "UPDATE pages SET content = ?, updated_at = ? WHERE title = ?",
                (new_content, now, title),
            )
        else:
            db.execute(
                "INSERT INTO pages (title, content, updated_at) VALUES (?, ?, ?)",
                (title, new_content, now),
            )
        db.commit()
        return redirect(url_for("view_page", title=title))

    return render_template(
        "edit.html",
        page=row,
        title=title,
        site_name=SITE_NAME,
    )


@app.route("/<path:title>/delete", methods=["POST"])
@login_required
def delete_page(title):
    db = get_db()
    db.execute("DELETE FROM pages WHERE title = ?", (title,))
    db.commit()
    return redirect(url_for("index"))


# ── Error handlers ──────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html", site_name=SITE_NAME), 404


# ── App bootstrap ───────────────────────────────────────────────────

app.teardown_appcontext(close_db)
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9527, debug=True)
