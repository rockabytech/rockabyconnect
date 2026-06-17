import os, sqlite3, re, random, string, json, shutil
from datetime import date, timedelta, datetime
from collections import defaultdict
from flask import Flask, render_template_string, request, redirect, url_for, session, make_response, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from PIL import Image

# ============================================================
# APP CONFIGURATION (DYNAMIC FOR RENDER)
# ============================================================
app = Flask(__name__)
app.secret_key = 'rockabytech-secret-key-change-in-production-2025'
app.permanent_session_lifetime = timedelta(days=30)

ADMIN_PASSWORD = 'Trythorous2909@1707#!'

# Dynamic paths for Render
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'providers.db')

# Upload folder
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

SKILL_SUGGESTIONS = [
    'Plumbing', 'Electrical', 'Carpentry', 'Painting', 'Cleaning',
    'Tutoring', 'Graphic Design', 'Web Development', 'Tailoring',
    'Cooking', 'Driving', 'Bricklaying', 'Construction', 'Boda Rider',
    'Maid', 'Gardening', 'Security Guard', 'Welding', 'Salon/Hair dressing',
    'Farming', 'Other'
]

FREELANCER_STATUSES = ['Available', 'Occupied', 'On Leave']
VENDOR_STATUSES = ['Open', 'Closed', 'Away']

# ============================================================
# IMAGE RESIZING HELPER
# ============================================================
def save_resized_image(file, max_width=800):
    """Resize image to max_width, save with unique name. Returns filename."""
    if not file or not file.filename:
        return None
    filename = secure_filename(file.filename)
    base, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.gif'):
        ext = '.jpg'
    new_filename = f"{base}_{os.urandom(4).hex()}{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
    try:
        img = Image.open(file.stream)
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.save(filepath, quality=85)
        return new_filename
    except Exception as e:
        print(f"Image resize error: {e}")
        return None

# ============================================================
# DATABASE SETUP
# ============================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000;")
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS providers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        skills TEXT,
        district TEXT,
        village TEXT,
        bio TEXT,
        profile_pic TEXT,
        status TEXT DEFAULT 'Available',
        featured INTEGER DEFAULT 0,
        featured_expiry DATE,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        business_name TEXT NOT NULL,
        district TEXT,
        village TEXT,
        landmark TEXT,
        bio TEXT,
        vendor_image TEXT,
        vendor_image2 TEXT,
        vendor_image3 TEXT,
        status TEXT DEFAULT 'Open',
        featured INTEGER DEFAULT 0,
        featured_expiry DATE,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employer_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        company TEXT,
        description TEXT,
        location TEXT,
        village TEXT,
        contact TEXT,
        status TEXT DEFAULT 'Open',
        posted_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        job_image TEXT,
        featured INTEGER DEFAULT 0,
        featured_expiry DATE,
        FOREIGN KEY(employer_id) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS boost_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        transaction_id TEXT NOT NULL,
        plan TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        boost_type TEXT DEFAULT 'profile',
        item_id INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_id INTEGER NOT NULL,
        reviewer_id INTEGER NOT NULL,
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(provider_id) REFERENCES providers(id),
        FOREIGN KEY(reviewer_id) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    conn.commit()
    conn.close()

# ============================================================
# HELPERS
# ============================================================
def get_db():
    """Get database connection (for routes that use it)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_phone_number(text):
    if not text:
        return False
    digits = ''.join(filter(str.isdigit, text))
    return (digits.startswith('07') and len(digits) == 10) or (digits.startswith('2567') and len(digits) == 12)

def whatsapp_link(phone):
    digits = ''.join(filter(str.isdigit, phone))
    if digits.startswith('0'):
        digits = '256' + digits[1:]
    elif not digits.startswith('256'):
        digits = '256' + digits
    return f"https://wa.me/{digits}"

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def is_featured_now(featured_flag, expiry_date):
    if not featured_flag:
        return False
    if expiry_date is None:
        return True
    return date.today() <= date.fromisoformat(expiry_date)

def add_notification(user_id, type, message):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA busy_timeout = 5000;")
        c = conn.cursor()
        c.execute("INSERT INTO notifications (user_id, type, message) VALUES (?,?,?)", (user_id, type, message))
        conn.commit()
        conn.close()
    except sqlite3.OperationalError as e:
        print(f"Notification failed: {e}")

# ============================================================
# BASE TEMPLATE (UNCHANGED)
# ============================================================
base_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RockabyConnect – {title}</title>
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#f5af19">
    {% raw %}
    <style>
        :root {
            --primary: #f5af19; --primary-dark: #e09e15;
            --bg: #f3f2ef; --card-bg: #ffffff; --text: #1a1a1a;
            --text-secondary: #666666; --border: #e0e0e0;
            --radius: 12px; --shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        * { margin:0; padding:0; box-sizing:border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg); color: var(--text); min-height: 100vh;
        }
        .navbar {
            background: var(--card-bg); box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            padding: 12px 20px; position: sticky; top: 0; z-index: 100;
            display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;
        }
        .navbar .logo { font-size: 1.5rem; font-weight: 700; color: var(--primary-dark); text-decoration: none; }
        .nav-links { display: flex; gap: 15px; flex-wrap: wrap; align-items: center; }
        .nav-links a {
            color: var(--text-secondary); text-decoration: none; font-weight: 500;
            padding: 8px 12px; border-radius: 6px; transition: background 0.2s;
        }
        .nav-links a:hover, .nav-links a.active { background: #f5f5f5; color: var(--text); }
        .btn {
            display: inline-block; padding: 10px 20px; background: var(--primary);
            color: #fff; border: none; border-radius: 6px; font-weight: 600;
            cursor: pointer; text-decoration: none; transition: background 0.2s;
        }
        .btn:hover { background: var(--primary-dark); }
        .btn-outline { background: transparent; border: 1px solid var(--primary); color: var(--primary-dark); }
        .btn-whatsapp { background: #25D366; color: white; margin-top: 10px; }
        .btn-small { padding: 5px 10px; font-size: 0.8rem; }
        .btn-danger { background: #dc3545; }
        .container { max-width: 800px; margin: 20px auto; padding: 0 15px; }
        .card {
            background: var(--card-bg); border-radius: var(--radius); padding: 24px;
            margin-bottom: 16px; box-shadow: var(--shadow); border: 1px solid var(--border);
        }
        .card-header { font-size: 1.2rem; font-weight: 600; margin-bottom: 15px; border-bottom: 1px solid var(--border); padding-bottom: 10px; }
        label { display: block; margin-top: 15px; font-weight: 500; }
        input, textarea, select {
            width: 100%; padding: 10px 12px; margin-top: 5px; border-radius: 6px;
            border: 1px solid var(--border); font-size: 0.95rem;
        }
        .hero {
            background: linear-gradient(135deg, #24243e, #302b63);
            color: white; padding: 40px 20px; text-align: center; border-radius: var(--radius);
            margin-bottom: 20px;
        }
        .hero h1 { font-size: 2rem; margin-bottom: 10px; }
        .hero p { margin-bottom: 20px; color: #ccc; }
        .category-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 15px; }
        .chip {
            background: var(--primary); color: white; padding: 5px 12px;
            border-radius: 20px; font-size: 0.85rem; text-decoration: none;
        }
        .chip:hover { background: var(--primary-dark); }
        .provider-card, .job-card, .vendor-card {
            display: flex; align-items: center; gap: 15px; padding: 15px 0;
            border-bottom: 1px solid var(--border);
        }
        .provider-card:last-child, .job-card:last-child, .vendor-card:last-child { border-bottom: none; }
        .provider-info, .job-info, .vendor-info { flex:1; }
        .provider-info h3, .job-info h3, .vendor-info h3 { margin:0; font-size:1.1rem; }
        .meta { color: var(--text-secondary); font-size:0.9rem; }
        .profile-pic { width: 80px; height: 80px; border-radius: 50%; object-fit: cover; border: 2px solid var(--primary); }
        .vendor-img { width: 180px; height: auto; max-height: 120px; object-fit: cover; border-radius: 8px; border: 1px solid var(--border); }
        .vendor-img-gallery { display: flex; gap: 10px; margin-top: 10px; }
        .vendor-img-gallery img { width: 100px; height: 80px; object-fit: cover; border-radius: 6px; }
        .badge {
            display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px;
            vertical-align: middle; color: white;
        }
        .badge-available { background: #28a745; }
        .badge-occupied { background: #ffc107; color: #333; }
        .badge-leave { background: #6c757d; }
        .badge-open { background: #17a2b8; }
        .badge-taken { background: #6f42c1; }
        .badge-closed { background: #dc3545; }
        .badge-away { background: #ffc107; color: #333; }
        .search-bar input { width: 100%; padding: 12px 15px; border-radius: 30px; border: 1px solid var(--border); margin-bottom: 20px; }
        footer { text-align: center; color: var(--text-secondary); padding: 30px 0; font-size: 0.9rem; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 8px; text-align: left; border-bottom: 1px solid var(--border); }
        .rating { color: var(--primary); font-size: 1.2rem; }
        .review-card { border-left: 3px solid var(--primary); padding: 10px; margin: 10px 0; background: #f9f9f9; }
        @media (max-width: 600px) {
            .navbar { flex-direction: column; gap: 10px; }
            .provider-card, .job-card, .vendor-card { flex-direction: column; align-items: flex-start; }
            .vendor-img { width: 100%; max-height: 180px; }
        }
    </style>
    {% endraw %}
</head>
<body>
    <nav class="navbar">
        <a href="/" class="logo" style="display:flex; align-items:center; gap:10px; text-decoration:none;">
    <img src="/static/icon-192.png" alt="RockabyConnect" style="height:40px; width:40px; border-radius:8px;">
    <div>
        <div style="font-size:1.3rem; font-weight:700; line-height:1.2;">ROCKABY<span style="color:var(--primary-dark);">CONNECT</span></div>
        <div style="font-size:0.7rem; color:var(--text-secondary); line-height:1;">Connecting Skills, Building Uganda</div>
    </div>
</a>
        <div class="nav-links">
            <a href="/" class="{{ 'active' if active_page == 'home' else '' }}">Home</a>
            {% if session.user_id %}
                <a href="/dashboard" class="{{ 'active' if active_page == 'dashboard' else '' }}">Dashboard</a>
            {% endif %}
            <a href="/list" class="{{ 'active' if active_page == 'list' else '' }}">Find Skills</a>
            <a href="/jobs" class="{{ 'active' if active_page == 'jobs' else '' }}">Jobs</a>
            <a href="/vendors" class="{{ 'active' if active_page == 'vendors' else '' }}">Vendors</a>
            {% if session.user_id %}
                <a href="/logout">Logout ({{ session.user_name }})</a>
            {% else %}
                <a href="/login" class="{{ 'active' if active_page == 'login' else '' }}">Login</a>
                <a href="/signup" class="{{ 'active' if active_page == 'signup' else '' }}">Sign Up</a>
            {% endif %}
        </div>
    </nav>
    <div class="container">
        {content}
    </div>
    <footer>
        &copy; 2025 RockabyTech – Connecting Uganda's Workforce
    </footer>
    <a href="https://wa.me/256751318876?text=Hi%20RockabyConnect%20Support" target="_blank" style="position:fixed; bottom:20px; right:20px; background:#25D366; color:white; width:60px; height:60px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:30px; box-shadow:0 4px 10px rgba(0,0,0,0.3); z-index:999; text-decoration:none;">💬</a>
    <script>
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/service-worker.js');
            });
        }
    </script>
</body>
</html>
"""
