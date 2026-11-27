"""生词本 —— 一个极简的个人背单词/好句网站。

两个板块：
  1. 单词：生词 + 释义 + 例句
  2. 句子：写作/翻译用的例句 + 解释，按用户自定义分类存放

技术栈：Flask + SQLite（标准库），密码用 werkzeug 哈希存储。
本地运行：python app.py
线上部署：gunicorn app:app（见 README.md）
"""
import os
import random
import re
import sqlite3
from functools import wraps

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 数据库文件路径可用环境变量覆盖，便于部署到有持久磁盘的平台
DATABASE = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "vocab.db"))
# 生产环境务必通过环境变量 SECRET_KEY 设置随机密钥
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

app = Flask(__name__)
app.secret_key = SECRET_KEY

MAX_BOX = 5  # 记忆熟练度最高档（Leitner 盒子数）
MIN_BOX = -3  # 熟练度最低档（负数 = 反复没记住，用红点表示）

# ---------------------------------------------------------------------------
# 复习推荐权重：控制「新词 / 旧词」的出现频率。
# 想调整的话直接改下面这几个数即可。
# ---------------------------------------------------------------------------
BOX_WEIGHT_BASE = 2        # 熟练度每升一档，出现概率减半：box0=32 … box5=1
NEW_WORD_BOOST = 2.0       # 从未复习过的新词再翻倍，保证新词优先
RECENT_COOLDOWN_MINUTES = 30  # 刚复习完这么多分钟内，几乎不再被抽到


# ---------------------------------------------------------------------------
# 数据库
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            word TEXT NOT NULL,
            example TEXT,
            meaning TEXT NOT NULL,
            box INTEGER NOT NULL DEFAULT 0,
            wrong_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            reviewed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            sentence TEXT NOT NULL,
            explanation TEXT,
            box INTEGER NOT NULL DEFAULT 0,
            wrong_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            reviewed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS phrases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            phrase TEXT NOT NULL,
            meaning TEXT NOT NULL,
            example TEXT,
            box INTEGER NOT NULL DEFAULT 0,
            wrong_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            reviewed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_words_user ON words(user_id);
        CREATE INDEX IF NOT EXISTS idx_categories_user ON categories(user_id);
        CREATE INDEX IF NOT EXISTS idx_sentences_user ON sentences(user_id);
        CREATE INDEX IF NOT EXISTS idx_phrases_user ON phrases(user_id);
        """
    )
    # 迁移：给 categories 增加 sort_order 列（老库升级用）
    cols = [r[1] for r in db.execute("PRAGMA table_info(categories)")]
    if "sort_order" not in cols:
        db.execute(
            "ALTER TABLE categories ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"
        )
    db.commit()
    db.close()


init_db()


# ---------------------------------------------------------------------------
# 登录校验
# ---------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("请先登录", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


# ---------------------------------------------------------------------------
# 认证相关路由
# ---------------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not username or not password:
            flash("用户名和密码不能为空", "error")
        elif len(username) > 30:
            flash("用户名太长（最多 30 个字符）", "error")
        elif len(password) < 6:
            flash("密码至少 6 位", "error")
        elif password != confirm:
            flash("两次输入的密码不一致", "error")
        else:
            db = get_db()
            exists = db.execute(
                "SELECT 1 FROM users WHERE username = ?", (username,)
            ).fetchone()
            if exists:
                flash("这个用户名已被注册", "error")
            else:
                db.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
                db.commit()
                flash("注册成功，请登录", "success")
                return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("用户名或密码错误", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("已退出登录", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# 单词板块
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    db = get_db()
    user_id = session["user_id"]
    total = db.execute(
        "SELECT COUNT(*) AS n FROM words WHERE user_id = ?", (user_id,)
    ).fetchone()["n"]
    new_count = db.execute(
        "SELECT COUNT(*) AS n FROM words WHERE user_id = ? AND reviewed_at IS NULL",
        (user_id,),
    ).fetchone()["n"]

    # 排序方式来自白名单，杜绝 SQL 注入
    sort_orders = {
        "time": "id DESC",                      # 按录入时间（新的在前）
        "alpha": "word COLLATE NOCASE ASC",     # 按字母（忽略大小写）
        "box": "box ASC, id DESC",              # 按熟练度（待学在前）
    }
    sort = request.args.get("sort", "time")
    if sort not in sort_orders:
        sort = "time"
    words = db.execute(
        f"SELECT * FROM words WHERE user_id = ? ORDER BY {sort_orders[sort]}",
        (user_id,),
    ).fetchall()
    return render_template(
        "index.html", words=words, total=total, new_count=new_count, sort=sort
    )


@app.route("/words/add", methods=["POST"])
@login_required
def add_word():
    word = request.form.get("word", "").strip()
    meaning = request.form.get("meaning", "").strip()
    example = request.form.get("example", "").strip()

    if not word or not meaning:
        flash("单词和释义不能为空", "error")
        return redirect(url_for("index"))

    db = get_db()
    exists = db.execute(
        "SELECT 1 FROM words WHERE user_id = ? AND LOWER(word) = LOWER(?)",
        (session["user_id"], word),
    ).fetchone()
    if exists:
        flash(f"「{word}」已存在，添加失败，请勿重复录入", "error")
        return redirect(url_for("index"))

    db.execute(
        "INSERT INTO words (user_id, word, example, meaning) VALUES (?, ?, ?, ?)",
        (session["user_id"], word, example, meaning),
    )
    db.commit()
    flash(f"已添加「{word}」", "success")
    return redirect(url_for("index"))


@app.route("/words/<int:word_id>/delete", methods=["POST"])
@login_required
def delete_word(word_id):
    db = get_db()
    db.execute(
        "DELETE FROM words WHERE id = ? AND user_id = ?",
        (word_id, session["user_id"]),
    )
    db.commit()
    flash("已删除", "success")
    return redirect(url_for("index"))


@app.route("/words/<int:word_id>/mark", methods=["POST"])
@login_required
def mark_word(word_id):
    remembered = request.form.get("remembered") == "1"
    sort = request.form.get("sort", "time")
    if sort not in {"time", "alpha", "box"}:
        sort = "time"
    return apply_mark("words", word_id, remembered, url_for("index", sort=sort))


def parse_word_line(line):
    """把一行 '单词 释义' 拆成 (单词, 释义)。支持 Tab / = / | / 多空格分隔。"""
    line = line.strip()
    if not line:
        return None
    for sep in ("\t", "=", "|"):
        if sep in line:
            word, _, meaning = line.partition(sep)
            word, meaning = word.strip(), meaning.strip()
            return (word, meaning) if word else None
    m = re.search(r"\s{2,}", line)
    if m:
        word, meaning = line[: m.start()].strip(), line[m.end():].strip()
        return (word, meaning) if word else None
    parts = line.split(" ", 1)
    if len(parts) == 2:
        word, meaning = parts[0].strip(), parts[1].strip()
        return (word, meaning) if word else None
    return (line, "")


@app.route("/words/bulk", methods=["POST"])
@login_required
def bulk_add_words():
    lines = [ln for ln in request.form.get("bulk", "").splitlines() if ln.strip()]
    db = get_db()
    # 已存在的单词（统一转小写比对），跳过重复，避免和之前录的冲突
    existing = {
        r[0]
        for r in db.execute(
            "SELECT LOWER(word) FROM words WHERE user_id = ?",
            (session["user_id"],),
        ).fetchall()
    }
    added = 0
    skipped_words = []
    for ln in lines:
        parsed = parse_word_line(ln)
        if not parsed or not parsed[1]:
            continue
        word, meaning = parsed
        if word.lower() in existing:
            skipped_words.append(word)
            continue
        db.execute(
            "INSERT INTO words (user_id, word, meaning) VALUES (?, ?, ?)",
            (session["user_id"], word, meaning),
        )
        existing.add(word.lower())
        added += 1
    db.commit()
    if skipped_words:
        dupes = "、".join(skipped_words[:10])
        more = f" 等 {len(skipped_words)} 个" if len(skipped_words) > 10 else ""
        if added:
            flash(f"有 {len(skipped_words)} 个重复单词未导入：{dupes}{more}（已导入 {added} 个）", "error")
        else:
            flash(f"这些单词都已存在，未导入：{dupes}{more}", "error")
    elif added:
        flash(f"批量导入了 {added} 个单词", "success")
    else:
        flash("没有导入任何单词，请检查格式", "error")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# 短语板块
# ---------------------------------------------------------------------------
@app.route("/phrases")
@login_required
def phrases():
    db = get_db()
    uid = session["user_id"]
    total = db.execute(
        "SELECT COUNT(*) AS n FROM phrases WHERE user_id = ?", (uid,)
    ).fetchone()["n"]
    new_count = db.execute(
        "SELECT COUNT(*) AS n FROM phrases WHERE user_id = ? AND reviewed_at IS NULL",
        (uid,),
    ).fetchone()["n"]
    rows = db.execute(
        "SELECT * FROM phrases WHERE user_id = ? ORDER BY id DESC", (uid,)
    ).fetchall()
    return render_template(
        "phrases.html", phrases=rows, total=total, new_count=new_count
    )


@app.route("/phrases/add", methods=["POST"])
@login_required
def add_phrase():
    phrase = request.form.get("phrase", "").strip()
    meaning = request.form.get("meaning", "").strip()
    example = request.form.get("example", "").strip()

    if not phrase or not meaning:
        flash("短语和释义不能为空", "error")
        return redirect(url_for("phrases"))

    db = get_db()
    db.execute(
        "INSERT INTO phrases (user_id, phrase, meaning, example) VALUES (?, ?, ?, ?)",
        (session["user_id"], phrase, meaning, example),
    )
    db.commit()
    flash(f"已添加「{phrase}」", "success")
    return redirect(url_for("phrases"))


@app.route("/phrases/<int:pid>/delete", methods=["POST"])
@login_required
def delete_phrase(pid):
    db = get_db()
    db.execute(
        "DELETE FROM phrases WHERE id = ? AND user_id = ?",
        (pid, session["user_id"]),
    )
    db.commit()
    flash("已删除", "success")
    return redirect(url_for("phrases"))


@app.route("/phrases/<int:pid>/mark", methods=["POST"])
@login_required
def mark_phrase(pid):
    remembered = request.form.get("remembered") == "1"
    return apply_mark("phrases", pid, remembered, url_for("phrases"))


@app.route("/phrases/bulk", methods=["POST"])
@login_required
def bulk_add_phrases():
    lines = [ln for ln in request.form.get("bulk", "").splitlines() if ln.strip()]
    db = get_db()
    added = 0
    for ln in lines:
        parsed = parse_word_line(ln)
        if not parsed or not parsed[1]:
            continue
        phrase, meaning = parsed
        db.execute(
            "INSERT INTO phrases (user_id, phrase, meaning) VALUES (?, ?, ?)",
            (session["user_id"], phrase, meaning),
        )
        added += 1
    db.commit()
    if added:
        flash(f"批量导入了 {added} 个短语", "success")
    else:
        flash("没有导入任何短语，请检查格式", "error")
    return redirect(url_for("phrases"))


# ---------------------------------------------------------------------------
# 句子板块（自定义分类）
# ---------------------------------------------------------------------------
@app.route("/sentences")
@login_required
def sentences():
    db = get_db()
    uid = session["user_id"]
    categories = db.execute(
        "SELECT id, name FROM categories WHERE user_id = ? ORDER BY sort_order, id",
        (uid,),
    ).fetchall()
    rows = db.execute(
        "SELECT id, category_id, sentence, explanation FROM sentences "
        "WHERE user_id = ? ORDER BY id DESC",
        (uid,),
    ).fetchall()

    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category_id"], []).append(r)

    return render_template(
        "sentences.html",
        categories=categories,
        by_cat=by_cat,
        total_sentences=len(rows),
    )


@app.route("/categories/add", methods=["POST"])
@login_required
def add_category():
    name = request.form.get("name", "").strip()
    if not name:
        flash("分类名不能为空", "error")
    elif len(name) > 30:
        flash("分类名太长（最多 30 个字符）", "error")
    else:
        db = get_db()
        exists = db.execute(
            "SELECT 1 FROM categories WHERE user_id = ? AND name = ?",
            (session["user_id"], name),
        ).fetchone()
        if exists:
            flash("已存在同名分类", "error")
        else:
            db.execute(
                "INSERT INTO categories (user_id, name, sort_order) "
                "VALUES (?, ?, (SELECT COALESCE(MAX(sort_order), 0) + 1 "
                "FROM categories WHERE user_id = ?))",
                (session["user_id"], name, session["user_id"]),
            )
            db.commit()
            flash(f"已新建分类「{name}」", "success")
    return redirect(url_for("sentences"))


@app.route("/categories/<int:cid>/rename", methods=["POST"])
@login_required
def rename_category(cid):
    name = request.form.get("name", "").strip()
    if not name:
        flash("分类名不能为空", "error")
        return redirect(url_for("sentences"))
    db = get_db()
    db.execute(
        "UPDATE categories SET name = ? WHERE id = ? AND user_id = ?",
        (name, cid, session["user_id"]),
    )
    db.commit()
    flash("分类已改名", "success")
    return redirect(url_for("sentences"))


@app.route("/categories/<int:cid>/delete", methods=["POST"])
@login_required
def delete_category(cid):
    db = get_db()
    db.execute(
        "DELETE FROM categories WHERE id = ? AND user_id = ?",
        (cid, session["user_id"]),
    )
    db.commit()
    flash("已删除分类及其下的所有句子", "success")
    return redirect(url_for("sentences"))


@app.route("/categories/<int:cid>/move/<direction>", methods=["POST"])
@login_required
def move_category(cid, direction):
    """上移/下移分类，通过重排 sort_order 实现。"""
    db = get_db()
    cats = db.execute(
        "SELECT id, sort_order FROM categories WHERE user_id = ? ORDER BY sort_order, id",
        (session["user_id"],),
    ).fetchall()
    ids = [c["id"] for c in cats]
    if cid not in ids:
        return redirect(url_for("sentences"))
    idx = ids.index(cid)
    swap = idx - 1 if direction == "up" else idx + 1
    if 0 <= swap < len(ids):
        ids[idx], ids[swap] = ids[swap], ids[idx]
        for i, cid2 in enumerate(ids):
            db.execute(
                "UPDATE categories SET sort_order = ? WHERE id = ? AND user_id = ?",
                (i, cid2, session["user_id"]),
            )
        db.commit()
    return redirect(url_for("sentences"))


@app.route("/sentences/add", methods=["POST"])
@login_required
def add_sentence():
    category_id = request.form.get("category_id")
    sentence = request.form.get("sentence", "").strip()
    explanation = request.form.get("explanation", "").strip()

    if not category_id or not sentence:
        flash("请选择分类并填写句子", "error")
        return redirect(url_for("sentences"))

    db = get_db()
    cat = db.execute(
        "SELECT 1 FROM categories WHERE id = ? AND user_id = ?",
        (category_id, session["user_id"]),
    ).fetchone()
    if cat is None:
        flash("分类不存在", "error")
        return redirect(url_for("sentences"))

    db.execute(
        "INSERT INTO sentences (user_id, category_id, sentence, explanation) "
        "VALUES (?, ?, ?, ?)",
        (session["user_id"], category_id, sentence, explanation),
    )
    db.commit()
    flash("已添加句子", "success")
    return redirect(url_for("sentences"))


@app.route("/sentences/<int:sid>/delete", methods=["POST"])
@login_required
def delete_sentence(sid):
    db = get_db()
    db.execute(
        "DELETE FROM sentences WHERE id = ? AND user_id = ?",
        (sid, session["user_id"]),
    )
    db.commit()
    flash("已删除", "success")
    return redirect(url_for("sentences"))


@app.route("/sentences/<int:sid>/edit", methods=["POST"])
@login_required
def edit_sentence(sid):
    category_id = request.form.get("category_id")
    sentence = request.form.get("sentence", "").strip()
    explanation = request.form.get("explanation", "").strip()

    if not category_id or not sentence:
        flash("分类和句子不能为空", "error")
        return redirect(url_for("sentences"))

    db = get_db()
    cat = db.execute(
        "SELECT 1 FROM categories WHERE id = ? AND user_id = ?",
        (category_id, session["user_id"]),
    ).fetchone()
    if cat is None:
        flash("分类不存在", "error")
        return redirect(url_for("sentences"))

    db.execute(
        "UPDATE sentences SET category_id = ?, sentence = ?, explanation = ? "
        "WHERE id = ? AND user_id = ?",
        (category_id, sentence, explanation, sid, session["user_id"]),
    )
    db.commit()
    flash("已保存修改", "success")
    return redirect(url_for("sentences"))


@app.route("/sentences/bulk", methods=["POST"])
@login_required
def bulk_add_sentences():
    category_id = request.form.get("category_id")
    text = request.form.get("bulk", "")

    db = get_db()
    cat = db.execute(
        "SELECT 1 FROM categories WHERE id = ? AND user_id = ?",
        (category_id, session["user_id"]),
    ).fetchone() if category_id else None
    if cat is None:
        flash("请选择分类", "error")
        return redirect(url_for("sentences"))

    lines = [ln for ln in text.splitlines() if ln.strip()]
    added = 0
    for ln in lines:
        sentence, _, explanation = ln.strip().partition("|")
        sentence, explanation = sentence.strip(), explanation.strip()
        if not sentence:
            continue
        db.execute(
            "INSERT INTO sentences (user_id, category_id, sentence, explanation) "
            "VALUES (?, ?, ?, ?)",
            (session["user_id"], category_id, sentence, explanation),
        )
        added += 1
    db.commit()
    if added:
        flash(f"批量导入了 {added} 句", "success")
    else:
        flash("没有导入任何句子", "error")
    return redirect(url_for("sentences"))


# ---------------------------------------------------------------------------
# 复习（回忆式卡片，支持单词 / 句子两种模式）
# ---------------------------------------------------------------------------
def blank_word(example, word):
    """把例句里的目标单词挖空，作为回忆提示。"""
    if not example or not word:
        return example or ""
    pattern = re.compile(re.escape(word), re.IGNORECASE)
    return pattern.sub("____", example)


def review_weight(box, hours_since):
    """计算某条内容在复习抽题中的权重。

    hours_since < 0 表示从未复习过（新词）；否则为距上次复习的小时数。
    规则：
      - 熟练度越低（box 越小）权重越高，每升一档减半；
      - 从未复习过的新词额外翻倍；
      - 刚复习完不久（冷却期内）几乎不再出现，随间隔拉长逐渐恢复。
    """
    fam = BOX_WEIGHT_BASE ** (MAX_BOX - box)
    if hours_since is None or hours_since < 0:
        recency = NEW_WORD_BOOST
    elif hours_since * 60 < RECENT_COOLDOWN_MINUTES:
        recency = 0.0
    elif hours_since < 6:
        recency = 0.2
    elif hours_since < 24:
        recency = 0.5
    elif hours_since < 72:
        recency = 0.8
    else:
        recency = 1.0
    return fam * recency


def box_dots(box):
    """把熟练度渲染成点串：负数（反复没记住）用红点，正数用主色实点，其余空点。"""
    neg = max(0, -box)
    pos = max(0, box)
    empty = max(0, MAX_BOX - pos)
    html = f'<span class="box-neg">{"●" * neg}</span>' if neg else ""
    html += "●" * pos
    html += "○" * empty
    return html


app.jinja_env.globals["box_dots"] = box_dots


def apply_answer(db, table, row, remembered):
    """把一次「记住/没记住」的结果写回 box / wrong_count / reviewed_at，返回新 box。

    table 必须是白名单内的表名（由调用方保证）。"""
    if remembered:
        new_box = min(MAX_BOX, row["box"] + 1)
        db.execute(
            f"UPDATE {table} SET box = ?, reviewed_at = datetime('now') WHERE id = ?",
            (new_box, row["id"]),
        )
    else:
        new_box = max(MIN_BOX, row["box"] - 1)
        db.execute(
            f"UPDATE {table} SET box = ?, wrong_count = wrong_count + 1, "
            "reviewed_at = datetime('now') WHERE id = ?",
            (new_box, row["id"]),
        )
    return new_box


def apply_mark(table, item_id, remembered, back):
    """列表页里的「记住/没记住」快捷标记：找到条目、写回、跳转回去。"""
    db = get_db()
    row = db.execute(
        f"SELECT * FROM {table} WHERE id = ? AND user_id = ?",
        (item_id, session["user_id"]),
    ).fetchone()
    if row is None:
        flash("内容不存在", "error")
    else:
        apply_answer(db, table, row, remembered)
        db.commit()
        flash("已标记「记住了」" if remembered else "已标记「没记住」", "success")
    return redirect(back)


@app.route("/review")
@login_required
def review():
    kind = request.args.get("type", "word")
    return render_template("review.html", type=kind)


@app.route("/api/review/next")
@login_required
def review_next():
    kind = request.args.get("type", "word")
    db = get_db()
    uid = session["user_id"]

    if kind == "sentence":
        rows = db.execute(
            "SELECT s.id, s.sentence, s.explanation, s.box, c.name AS category, "
            "CASE WHEN s.reviewed_at IS NULL THEN -1 "
            "ELSE (julianday('now') - julianday(s.reviewed_at)) * 24 END AS hours_since "
            "FROM sentences s JOIN categories c ON c.id = s.category_id "
            "WHERE s.user_id = ?",
            (uid,),
        ).fetchall()
    elif kind == "phrase":
        rows = db.execute(
            "SELECT id, phrase AS word, example, meaning, box, "
            "CASE WHEN reviewed_at IS NULL THEN -1 "
            "ELSE (julianday('now') - julianday(reviewed_at)) * 24 END AS hours_since "
            "FROM phrases WHERE user_id = ?",
            (uid,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, word, example, meaning, box, "
            "CASE WHEN reviewed_at IS NULL THEN -1 "
            "ELSE (julianday('now') - julianday(reviewed_at)) * 24 END AS hours_since "
            "FROM words WHERE user_id = ?",
            (uid,),
        ).fetchall()

    if not rows:
        return jsonify({"done": True, "type": kind})

    # 按「熟练度 + 距上次复习时长」加权抽题：新词优先、旧词少出现、刚复习过的冷却
    weights = [review_weight(r["box"], r["hours_since"]) for r in rows]
    if sum(weights) <= 0:
        # 全部都在冷却期内时，退化为等概率，避免无题可抽
        weights = [1.0] * len(rows)
    card = random.choices(rows, weights=weights, k=1)[0]

    if kind == "sentence":
        return jsonify(
            {
                "done": False,
                "type": "sentence",
                "id": card["id"],
                "category": card["category"],
                "sentence": card["sentence"],
                "explanation": card["explanation"],
                "box": card["box"],
            }
        )

    return jsonify(
        {
            "done": False,
            "type": kind,
            "id": card["id"],
            "word": card["word"],
            "example": card["example"],
            "example_blank": blank_word(card["example"], card["word"]),
            "meaning": card["meaning"],
            "box": card["box"],
        }
    )


@app.route("/api/review/answer", methods=["POST"])
@login_required
def review_answer():
    data = request.get_json(silent=True) or {}
    item_id = data.get("id")
    remembered = bool(data.get("remembered"))
    kind = data.get("type", "word")
    # 表名来自白名单，避免拼接任意 SQL
    table = {"sentence": "sentences", "phrase": "phrases"}.get(kind, "words")

    db = get_db()
    row = db.execute(
        f"SELECT * FROM {table} WHERE id = ? AND user_id = ?",
        (item_id, session["user_id"]),
    ).fetchone()

    if row is None:
        return jsonify({"ok": False, "error": "内容不存在"}), 404

    new_box = apply_answer(db, table, row, remembered)
    db.commit()

    return jsonify({"ok": True, "box": new_box})


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
