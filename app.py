"""安飞智能科技 - 知识库系统 (Knowledge Base)
支持 wiki.db + Obsidian knowledge-vault 双数据源"""
import sqlite3
import os
import glob
from datetime import datetime

from flask import (
    Flask, g, render_template, request, redirect,
    session, url_for, abort,
)
import markdown

app = Flask(__name__)
app.secret_key = "wiki-227578-secret-key-anfei-2026"
DB_PATH = os.path.join(os.path.dirname(__file__), "wiki.db")
VAULT_PATH = os.path.expanduser("~/knowledge-vault")
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


# ── Knowledge Vault helpers ─────────────────────────────────────────

def list_vault_files():
    """列出 knowledge-vault 中所有 .md 文件，按文件夹分组"""
    if not os.path.exists(VAULT_PATH):
        return []
    files = []
    for md in glob.glob(os.path.join(VAULT_PATH, "**/*.md"), recursive=True):
        rel = os.path.relpath(md, VAULT_PATH)
        title = rel[:-3]  # 去掉 .md
        folder = os.path.dirname(rel)
        stat = os.stat(md)
        files.append({
            "title": title,
            "display": os.path.basename(rel)[:-3],
            "folder": folder if folder else ".",
            "updated_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "source": "vault",
        })
    # 按文件夹排序
    files.sort(key=lambda f: (f["folder"], f["title"]))
    return files


def read_vault_file(title):
    """读取 knowledge-vault 中的 .md 文件"""
    path = os.path.join(VAULT_PATH, title + ".md")
    # 也支持子目录路径
    alt_path = os.path.join(VAULT_PATH, title, "index.md")
    for p in (path, alt_path):
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            stat = os.stat(p)
            return {
                "title": title,
                "content": content,
                "updated_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
    return None


def write_vault_file(title, content):
    """写入 knowledge-vault 中的 .md 文件"""
    path = os.path.join(VAULT_PATH, title + ".md")
    # 确保目录存在
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


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
    db_pages = db.execute(
        "SELECT title, updated_at FROM pages ORDER BY updated_at DESC"
    ).fetchall()
    vault_files = list_vault_files()

    # 合并：db 页面 + vault 文件
    all_pages = []
    for p in db_pages:
        all_pages.append({
            "title": p["title"],
            "folder": "📝 自定义页面",
            "updated_at": p["updated_at"],
            "source": "db",
        })
    for f in vault_files:
        folder_display = f["folder"] if f["folder"] != "." else "📁 知识库"
        all_pages.append({
            "title": f["title"],
            "folder": folder_display,
            "updated_at": f["updated_at"],
            "source": "vault",
        })

    # 按文件夹分组
    from collections import defaultdict
    grouped = defaultdict(list)
    for p in all_pages:
        grouped[p["folder"]].append(p)

    return render_template("index.html", grouped=dict(grouped), site_name=SITE_NAME)


@app.route("/<path:title>")
@login_required
def view_page(title):
    # 先查 wiki.db
    db = get_db()
    row = db.execute(
        "SELECT title, content, updated_at FROM pages WHERE title = ?",
        (title,),
    ).fetchone()

    if row:
        html = markdown.markdown(row["content"], extensions=["fenced_code", "codehilite"])
        return render_template(
            "view.html",
            page=row,
            html=html,
            source="db",
            site_name=SITE_NAME,
        )

    # 再查 knowledge-vault
    vf = read_vault_file(title)
    if vf:
        # 去掉 frontmatter (---\n...\n---)
        content = vf["content"]
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                content = content[end + 3:].strip()
        html = markdown.markdown(content, extensions=["fenced_code", "codehilite"])
        return render_template(
            "view.html",
            page=vf,
            html=html,
            source="vault",
            site_name=SITE_NAME,
        )

    abort(404)


@app.route("/<path:title>/edit", methods=["GET", "POST"])
@login_required
def edit_page(title):
    # 查来源
    db = get_db()
    db_row = db.execute(
        "SELECT title, content FROM pages WHERE title = ?", (title,)
    ).fetchone()
    vf = read_vault_file(title) if not db_row else None
    current_content = db_row["content"] if db_row else (vf["content"] if vf else "")
    is_vault = vf is not None and db_row is None

    if request.method == "POST":
        new_content = request.form.get("content", "")
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        if is_vault:
            # 写回 knowledge-vault
            write_vault_file(title, new_content)
        elif db_row:
            db.execute(
                "UPDATE pages SET content = ?, updated_at = ? WHERE title = ?",
                (new_content, now, title),
            )
        else:
            db.execute(
                "INSERT INTO pages (title, content, updated_at) VALUES (?, ?, ?)",
                (title, new_content, now),
            )
        if not is_vault:
            db.commit()
        return redirect(url_for("view_page", title=title))

    return render_template(
        "edit.html",
        page={"title": title, "content": current_content},
        title=title,
        is_vault=is_vault,
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
