import os, sqlite3, re, random, string, json, shutil
from flask import Flask, render_template_string, request, redirect, url_for, session, make_response, send_from_directory, send_file
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
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1 GB
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

# Backup directory for admin backups
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')
os.makedirs(BACKUP_DIR, exist_ok=True)

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
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA journal_mode=WAL;")   # <-- ADD THIS
    c = conn.cursor()   # <-- THIS LINE MUST BE PRESENT

    # ---- USERS TABLE ----
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        password_hash TEXT NOT NULL
    )''')

    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    if 'theme' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN theme TEXT DEFAULT 'default'")

    # ---- PROVIDERS TABLE ----
    c.execute('''CREATE TABLE IF NOT EXISTS providers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE NOT NULL,
        skills TEXT,
        district TEXT,
        village TEXT,
        bio TEXT,
        profile_pic TEXT,
        video TEXT,
        status TEXT DEFAULT 'Available',
        featured INTEGER DEFAULT 0,
        featured_expiry DATE,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # ---- VENDORS TABLE ----
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
        video TEXT,
        status TEXT DEFAULT 'Open',
        featured INTEGER DEFAULT 0,
        featured_expiry DATE,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # ---- JOBS TABLE ----
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
        video TEXT,
        featured INTEGER DEFAULT 0,
        featured_expiry DATE,
        FOREIGN KEY(employer_id) REFERENCES users(id)
    )''')

    # ---- BOOST REQUESTS TABLE ----
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

    # ---- REVIEWS TABLE ----
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

    # ---- NOTIFICATIONS TABLE (with is_read and link) ----
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT NOT NULL,
        message TEXT NOT NULL,
        link TEXT,
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # Add is_read column if missing
    c.execute("PRAGMA table_info(notifications)")
    cols = [row[1] for row in c.fetchall()]
    if 'is_read' not in cols:
        c.execute("ALTER TABLE notifications ADD COLUMN is_read INTEGER DEFAULT 0")
    if 'link' not in cols:
        c.execute("ALTER TABLE notifications ADD COLUMN link TEXT")

    # ---- REFERRAL TABLES ----
    c.execute('''CREATE TABLE IF NOT EXISTS referral_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        code TEXT NOT NULL UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER NOT NULL,
        referred_user_id INTEGER,
        referred_phone TEXT,
        status TEXT DEFAULT 'pending',
        reward_amount REAL DEFAULT 0,
        reward_type TEXT DEFAULT 'discount',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        FOREIGN KEY(referrer_id) REFERENCES users(id),
        FOREIGN KEY(referred_user_id) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS referral_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reward_percentage INTEGER DEFAULT 10,
        reward_fixed_amount REAL DEFAULT 0,
        reward_type TEXT DEFAULT 'discount',
        max_referrals INTEGER DEFAULT 10,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute("SELECT COUNT(*) FROM referral_settings")
    if c.fetchone()[0] == 0:
        c.execute("""
            INSERT INTO referral_settings (reward_percentage, reward_fixed_amount, reward_type, max_referrals, is_active)
            VALUES (10, 0, 'discount', 10, 1)
        """)

    # ---- JOB APPLICATIONS TABLE ----
    c.execute('''CREATE TABLE IF NOT EXISTS job_applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        applicant_id INTEGER NOT NULL,
        message TEXT,
        attachment TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(job_id) REFERENCES jobs(id),
        FOREIGN KEY(applicant_id) REFERENCES users(id)
    )''')

    # ---- APPLICATION NOTES TABLE ----
    c.execute('''CREATE TABLE IF NOT EXISTS application_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL,
        note TEXT NOT NULL,
        created_by INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(application_id) REFERENCES job_applications(id),
        FOREIGN KEY(created_by) REFERENCES users(id)
    )''')

    # ---- MESSAGES TABLE ----
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(sender_id) REFERENCES users(id),
        FOREIGN KEY(receiver_id) REFERENCES users(id)
    )''')

    # ---- VIDEO COLUMN FIX (for existing databases) ----
    for table in ['providers', 'vendors', 'jobs']:
        c.execute(f"PRAGMA table_info({table})")
        existing = [row[1] for row in c.fetchall()]
        if 'video' not in existing:
            c.execute(f"ALTER TABLE {table} ADD COLUMN video TEXT")

    conn.commit()
    conn.close()

init_db()

# ============================================================
# HELPERS
# ============================================================
def get_db():
    """Get database connection (for routes that use it)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.row_factory = sqlite3.Row
    return conn

# ===== INSERT THE CONTEXT MANAGER RIGHT HERE =====
import contextlib

@contextlib.contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")   # 30 seconds
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
# ===== END INSERT =====

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
        conn.execute("PRAGMA busy_timeout = 30000;")
        c = conn.cursor()
        c.execute("INSERT INTO notifications (user_id, type, message) VALUES (?,?,?)", (user_id, type, message))
        conn.commit()
        conn.close()
    except sqlite3.OperationalError as e:
        print(f"Notification failed: {e}")

def generate_referral_code(user_id):
    """Generate a unique referral code for a user"""
    import hashlib
    code = f"REF-{hashlib.md5(f'{user_id}{datetime.now().timestamp()}'.encode()).hexdigest()[:6].upper()}"
    return code

def get_referral_code(user_id):
    """Get or create referral code for a user"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    c.execute("SELECT code FROM referral_codes WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        conn.close()
        return row[0]
    # Generate new code
    code = generate_referral_code(user_id)
    c.execute("INSERT INTO referral_codes (user_id, code) VALUES (?,?)", (user_id, code))
    conn.commit()
    conn.close()
    return code

def get_referral_stats(user_id):
    """Get referral statistics for a user"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,)).fetchone()[0]
    pending = c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND status='pending'", (user_id,)).fetchone()[0]
    completed = c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND status='completed'", (user_id,)).fetchone()[0]
    rewarded = c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND status='rewarded'", (user_id,)).fetchone()[0]
    total_rewards = c.execute("SELECT COALESCE(SUM(reward_amount),0) FROM referrals WHERE referrer_id=? AND status='rewarded'", (user_id,)).fetchone()[0]
    conn.close()
    return {
        'total': total,
        'pending': pending,
        'completed': completed,
        'rewarded': rewarded,
        'total_rewards': total_rewards
    }

def process_referral(user_id, phone):
    """
    Check if there's a referral code in session, and if so,
    create a referral record for the new user signing up.
    """
    if 'referral_code' not in session:
        return False
    
    ref_code = session['referral_code']
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    
    # Find the referrer (user who owns this referral code)
    c.execute("SELECT user_id FROM referral_codes WHERE code = ?", (ref_code,))
    referrer = c.fetchone()
    if not referrer:
        conn.close()
        return False
    
    referrer_id = referrer[0]
    
    # Prevent self-referral
    if referrer_id == user_id:
        conn.close()
        return False
    
    # Check if this user has already been referred by this referrer
    c.execute("SELECT id FROM referrals WHERE referrer_id = ? AND referred_user_id = ?", (referrer_id, user_id))
    if c.fetchone():
        conn.close()
        return False
    
    # Get referral settings
    c.execute("SELECT reward_percentage, reward_type, max_referrals FROM referral_settings WHERE is_active=1 LIMIT 1")
    settings = c.fetchone()
    if not settings:
        settings = (10, 'discount', 10)  # Default: 10%, discount, max 10 referrals
    
    reward_percentage, reward_type, max_referrals = settings
    
    # Count completed referrals for this referrer
    count = c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND status IN ('completed', 'rewarded')", (referrer_id,)).fetchone()[0]
    if count >= max_referrals:
        conn.close()
        return False
    
    # Insert pending referral
    c.execute("""
        INSERT INTO referrals (referrer_id, referred_user_id, referred_phone, status, reward_amount, reward_type)
        VALUES (?, ?, ?, 'pending', 0, ?)
    """, (referrer_id, user_id, phone, reward_type))
    conn.commit()
    conn.close()
    

def save_resized_image(file, max_width=800, max_height=600, quality=85):
    """Resize image to uniform 800x600 cover (crop to fit) and save."""
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
        # Convert to RGB if needed
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        # Resize to cover the target dimensions (crop)
        target_ratio = max_width / max_height
        img_ratio = img.width / img.height
        if img_ratio > target_ratio:
            # Image is wider – crop width
            new_height = max_height
            new_width = int(max_height * img_ratio)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            left = (new_width - max_width) // 2
            img = img.crop((left, 0, left + max_width, max_height))
        else:
            # Image is taller – crop height
            new_width = max_width
            new_height = int(max_width / img_ratio)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            top = (new_height - max_height) // 2
            img = img.crop((0, top, max_width, top + max_height))
        img.save(filepath, quality=quality, optimize=True)
        return new_filename
    except Exception as e:
        print(f"Image resize error: {e}")
        return None

ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'ogg', 'mov', 'avi', 'mkv'}

def allowed_video(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS

# ============================================================
# THEME HELPERS
# ============================================================
def get_user_theme(user_id):
    """Get the user's theme preference (default: 'default')"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    c.execute("SELECT theme FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 'default'

def set_user_theme(user_id, theme):
    """Set the user's theme preference with proper connection handling"""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)  # 10-second timeout
        conn.execute("PRAGMA busy_timeout = 30000;")
        c = conn.cursor()
        # Ensure column exists
        c.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in c.fetchall()]
        if 'theme' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN theme TEXT DEFAULT 'default'")
        # Update
        c.execute("UPDATE users SET theme=? WHERE id=?", (theme, user_id))
        conn.commit()
    except sqlite3.OperationalError as e:
        print(f"[ERROR] set_user_theme failed: {e}")
    finally:
        if conn:
            conn.close()

def render_user_template(template, title="", active_page="", **kwargs):
    theme_class = ''
    if 'user_id' in session:
        if 'user_theme' in session:
            theme = session['user_theme']
        else:
            theme = get_user_theme(session['user_id'])
            session['user_theme'] = theme
        if theme and theme != 'default':
            theme_class = f"theme-{theme}"
    
    if theme_class:
        template = template.replace('<body>', f'<body class="{theme_class}">')
        template = template.replace('<body class="">', f'<body class="{theme_class}">')
    else:
        template = template.replace('<body class="theme-neon">', '<body>')
        template = template.replace('<body class="{theme_class}">', '<body>')
    
    if '{title}' in template:
        template = template.replace('{title}', title)
    if '{active_page}' in template:
        template = template.replace('{active_page}', active_page)
    for key, value in kwargs.items():
        template = template.replace(f'{{{key}}}', str(value))
    
    return render_template_string(template)

# ============================================================
# REFERRAL HELPERS
# ============================================================
import hashlib

def generate_referral_code(user_id):
    """Generate a unique referral code for a user"""
    code = f"REF-{hashlib.md5(f'{user_id}{datetime.now().timestamp()}'.encode()).hexdigest()[:6].upper()}"
    return code

def get_referral_code(user_id):
    """Get or create referral code for a user"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    c.execute("SELECT code FROM referral_codes WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        conn.close()
        return row[0]
    # Generate new code
    code = generate_referral_code(user_id)
    c.execute("INSERT INTO referral_codes (user_id, code) VALUES (?,?)", (user_id, code))
    conn.commit()
    conn.close()
    return code

def get_referral_stats(user_id):
    """Get referral statistics for a user"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,)).fetchone()[0]
    pending = c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND status='pending'", (user_id,)).fetchone()[0]
    completed = c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND status='completed'", (user_id,)).fetchone()[0]
    rewarded = c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND status='rewarded'", (user_id,)).fetchone()[0]
    total_rewards = c.execute("SELECT COALESCE(SUM(reward_amount),0) FROM referrals WHERE referrer_id=? AND status='rewarded'", (user_id,)).fetchone()[0]
    conn.close()
    return {
        'total': total,
        'pending': pending,
        'completed': completed,
        'rewarded': rewarded,
        'total_rewards': total_rewards
    }

def process_referral(user_id, phone):
    """
    Check if there's a referral code in session, and if so,
    create a referral record for the new user signing up.
    """
    if 'referral_code' not in session:
        return False
    
    ref_code = session['referral_code']
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    
    # Find the referrer (user who owns this referral code)
    c.execute("SELECT user_id FROM referral_codes WHERE code = ?", (ref_code,))
    referrer = c.fetchone()
    if not referrer:
        conn.close()
        return False
    
    referrer_id = referrer[0]
    
    # Prevent self-referral
    if referrer_id == user_id:
        conn.close()
        return False
    
    # Check if this user has already been referred by this referrer
    c.execute("SELECT id FROM referrals WHERE referrer_id = ? AND referred_user_id = ?", (referrer_id, user_id))
    if c.fetchone():
        conn.close()
        return False
    
    # Get referral settings
    c.execute("SELECT reward_percentage, reward_type, max_referrals FROM referral_settings WHERE is_active=1 LIMIT 1")
    settings = c.fetchone()
    if not settings:
        settings = (10, 'discount', 10)  # Default
    
    reward_percentage, reward_type, max_referrals = settings
    
    # Count completed referrals for this referrer
    count = c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND status IN ('completed', 'rewarded')", (referrer_id,)).fetchone()[0]
    if count >= max_referrals:
        conn.close()
        return False
    
    # Insert pending referral
    c.execute("""
        INSERT INTO referrals (referrer_id, referred_user_id, referred_phone, status, reward_amount, reward_type)
        VALUES (?, ?, ?, 'pending', 0, ?)
    """, (referrer_id, user_id, phone, reward_type))
    conn.commit()
    conn.close()

   # ============================================================
# NOTIFICATION HELPERS
# ============================================================

def add_notification(user_id, type, message, link=None):
    """Add a notification for a user."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA busy_timeout = 30000;")
        c = conn.cursor()
        c.execute(
            "INSERT INTO notifications (user_id, type, message, link, is_read) VALUES (?,?,?,?,0)",
            (user_id, type, message, link)
        )
        conn.commit()
        conn.close()
    except sqlite3.OperationalError as e:
        print(f"Notification failed: {e}")

def get_unread_notifications(user_id):
    """Get count of unread notifications for a user."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_notifications(user_id, limit=20):
    """Get recent notifications for a user, newest first."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, type, message, link, is_read, created_at
        FROM notifications
        WHERE user_id=?
        ORDER BY created_at DESC
        LIMIT ?
    """, (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows

def mark_notification_read(notification_id, user_id):
    """Mark a notification as read."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (notification_id, user_id))
    conn.commit()
    conn.close()
    
    # Clear the session
    session.pop('referral_code', None)
    
    return True

# ============================================================
# JOB APPLICATIONS ROUTES
# ============================================================

def get_application_status_badge(status):
    colors = {
        'pending': '#ffc107',
        'reviewed': '#17a2b8',
        'shortlisted': '#28a745',
        'rejected': '#dc3545',
        'hired': '#6f42c1'
    }
    return f'<span class="badge" style="background:{colors.get(status, "#6c757d")}; color:white;">{status.title()}</span>'

def get_user_name(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 'Unknown'

def get_unread_count(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages WHERE receiver_id=? AND is_read=0", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count


# ============================================================
# ADMIN REFERRAL SETTINGS
# ============================================================
@app.route('/admin/referral-settings', methods=['GET', 'POST'])
def admin_referral_settings_page():  # ← Renamed to avoid conflict
    if not session.get('admin'):
        return redirect('/admin/login')
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    
    # Get current settings
    c.execute("SELECT id, reward_percentage, reward_fixed_amount, reward_type, max_referrals, is_active FROM referral_settings LIMIT 1")
    settings = c.fetchone()
    if not settings:
        c.execute("INSERT INTO referral_settings (reward_percentage, reward_fixed_amount, reward_type, max_referrals) VALUES (10, 0, 'discount', 10)")
        conn.commit()
        c.execute("SELECT id, reward_percentage, reward_fixed_amount, reward_type, max_referrals, is_active FROM referral_settings LIMIT 1")
        settings = c.fetchone()
    
    if request.method == 'POST':
        c.execute("""
            UPDATE referral_settings SET
                reward_percentage=?, reward_fixed_amount=?, reward_type=?, max_referrals=?, is_active=?
            WHERE id=?
        """, (
            int(request.form.get('reward_percentage', 10)),
            float(request.form.get('reward_fixed_amount', 0)),
            request.form.get('reward_type', 'discount'),
            int(request.form.get('max_referrals', 10)),
            1 if request.form.get('is_active') else 0,
            settings[0]
        ))
        conn.commit()
        conn.close()
        return redirect('/admin/referral-settings')
    
    conn.close()
    
    sid, reward_percentage, reward_fixed_amount, reward_type, max_referrals, is_active = settings
    
    content = f'''
    <div class="card">
        <div class="card-header">🎁 Referral Program Settings</div>
        <form method="POST">
            <label>Reward Type</label>
            <select name="reward_type">
                <option value="discount" {"selected" if reward_type == 'discount' else ""}>Discount</option>
                <option value="credit" {"selected" if reward_type == 'credit' else ""}>Credit</option>
            </select>
            <label>Reward Percentage (%) of referred user's first payment</label>
            <input type="number" name="reward_percentage" value="{reward_percentage}" min="0" max="100">
            <label>Fixed Reward Amount (UGX) – leave 0 if using percentage</label>
            <input type="number" name="reward_fixed_amount" value="{reward_fixed_amount}" step="100" min="0">
            <label>Max Referrals per user</label>
            <input type="number" name="max_referrals" value="{max_referrals}" min="1" max="100">
            <label>
                <input type="checkbox" name="is_active" {"checked" if is_active else ""}>
                Active (allow referrals)
            </label>
            <button type="submit" class="btn" style="margin-top:20px;">Save Settings</button>
        </form>
        <div style="margin-top:20px;">
            <a href="/admin/dashboard" class="btn btn-outline">Back to Dashboard</a>
        </div>
    </div>
    '''
    return render_template_string(admin_base_template.replace("{title}", "Referral Settings").replace("{active_page}", "stats").replace("{content}", content))

# ============================================================
# BASE TEMPLATE (UNCHANGED)
# ============================================================
base_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>RockabyConnect – {title}</title>
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#f5af19">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        /* ================================================
           DEFAULT STYLES (YOUR ORIGINAL DESIGN)
           ================================================ */
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --primary: #f5af19;
            --primary-dark: #e09e15;
            --primary-light: #f7c35c;
            --secondary: #1a73e8;
            --bg: #f0f4f8;
            --card-bg: rgba(255, 255, 255, 0.85);
            --glass-border: rgba(255, 255, 255, 0.3);
            --text: #1a1a1a;
            --text-secondary: #666;
            --border: #e0e0e0;
            --radius: 20px;
            --shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
            --shadow-hover: 0 12px 48px rgba(0, 0, 0, 0.12);
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        body.dark-mode {
            --bg: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.85);
            --glass-border: rgba(255, 255, 255, 0.08);
            --text: #f1f5f9;
            --text-secondary: #94a3b8;
            --border: #334155;
            --shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(245, 175, 25, 0.08) 0%, transparent 50%),
                radial-gradient(circle at 90% 80%, rgba(26, 115, 232, 0.08) 0%, transparent 50%);
            color: var(--text);
            min-height: 100vh;
            transition: var(--transition);
        }

        .navbar {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--glass-border);
            padding: 16px 24px;
            position: sticky;
            top: 0;
            z-index: 1000;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 15px;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
        }

        .logo img {
            height: 45px;
            width: 45px;
            border-radius: 12px;
            object-fit: cover;
            box-shadow: 0 4px 15px rgba(245, 175, 25, 0.3);
        }

        .logo-text {
            font-size: 1.3rem;
            font-weight: 800;
            line-height: 1.2;
        }
        .logo-text span { color: var(--primary); }
        .logo-sub {
            font-size: 0.7rem;
            color: var(--text-secondary);
            line-height: 1;
        }

        .nav-links {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            align-items: center;
        }
        .nav-links a {
            color: var(--text-secondary);
            text-decoration: none;
            font-weight: 500;
            padding: 8px 16px;
            border-radius: 12px;
            transition: var(--transition);
            font-size: 0.95rem;
            position: relative;
        }
        .nav-links a:hover,
        .nav-links a.active {
            background: rgba(245, 175, 25, 0.15);
            color: var(--primary);
        }

        .nav-links .badge {
            background: #dc3545;
            color: white;
            font-size: 0.65rem;
            padding: 2px 6px;
            border-radius: 10px;
            margin-left: 4px;
            vertical-align: top;
            display: none;
        }

        .theme-toggle {
            background: rgba(245, 175, 25, 0.1);
            border: 1px solid var(--glass-border);
            border-radius: 50%;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 1.2rem;
            transition: var(--transition);
            color: var(--text);
        }
        .theme-toggle:hover {
            background: rgba(245, 175, 25, 0.2);
            transform: scale(1.05);
        }

        .hamburger {
            display: none;
            background: none;
            border: none;
            font-size: 1.8rem;
            cursor: pointer;
            color: var(--text);
        }

        .container {
            max-width: 1200px;
            margin: 24px auto;
            padding: 0 20px;
        }

        .card {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border-radius: var(--radius);
            padding: 28px;
            margin-bottom: 24px;
            box-shadow: var(--shadow);
            border: 1px solid var(--glass-border);
            transition: var(--transition);
        }
        .card:hover {
            transform: translateY(-4px);
            box-shadow: var(--shadow-hover);
        }
        .card-header {
            font-size: 1.3rem;
            font-weight: 700;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 2px solid var(--primary);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .hero {
            background: linear-gradient(135deg, rgba(245, 175, 25, 0.15), rgba(26, 115, 232, 0.15));
            backdrop-filter: blur(10px);
            border-radius: var(--radius);
            padding: 60px 40px;
            text-align: center;
            margin-bottom: 30px;
            border: 1px solid var(--glass-border);
        }
        .hero h1 {
            font-size: 2.5rem;
            margin-bottom: 15px;
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .hero p {
            font-size: 1.1rem;
            color: var(--text-secondary);
            margin-bottom: 25px;
        }

        .btn {
            display: inline-block;
            padding: 12px 28px;
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: white;
            border: none;
            border-radius: 12px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            font-size: 0.95rem;
            transition: var(--transition);
            box-shadow: 0 4px 15px rgba(245, 175, 25, 0.3);
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(245, 175, 25, 0.4);
        }
        .btn-outline {
            background: transparent;
            border: 2px solid var(--primary);
            color: var(--primary);
            box-shadow: none;
        }
        .btn-outline:hover {
            background: rgba(245, 175, 25, 0.1);
        }
        .btn-whatsapp {
            background: linear-gradient(135deg, #25D366, #128C7E);
            box-shadow: 0 4px 15px rgba(37, 211, 102, 0.3);
        }
        .btn-small {
            padding: 6px 14px;
            font-size: 0.85rem;
        }
        .btn-danger {
            background: linear-gradient(135deg, #dc3545, #c82333);
        }

        .stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border-radius: var(--radius);
            padding: 28px 20px;
            text-align: center;
            border: 1px solid var(--glass-border);
            transition: var(--transition);
            position: relative;
            overflow: hidden;
        }
        .stat-card::before {
            content: '';
            position: absolute;
            top: -30px;
            right: -30px;
            width: 80px;
            height: 80px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            opacity: 0.1;
            border-radius: 50%;
        }
        .stat-card h3 {
            font-size: 2.5rem;
            font-weight: 800;
            color: var(--primary);
            margin-bottom: 8px;
        }
        .stat-card small {
            color: var(--text-secondary);
            font-size: 0.9rem;
        }

        .category-chips {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 20px;
            justify-content: center;
        }
        .chip {
            background: rgba(245, 175, 25, 0.2);
            backdrop-filter: blur(5px);
            color: var(--text);
            font-weight: 600;
            padding: 6px 18px;
            border-radius: 30px;
            font-size: 0.85rem;
            text-decoration: none;
            transition: var(--transition);
            border: 1px solid var(--glass-border);
        }
        .chip:hover {
            background: var(--primary);
            color: white;
            transform: translateY(-2px);
        }

        .provider-card, .job-card, .vendor-card {
            display: flex;
            align-items: center;
            gap: 20px;
            padding: 20px 0;
            border-bottom: 1px solid var(--border);
            transition: var(--transition);
        }
        .provider-card:last-child, .job-card:last-child, .vendor-card:last-child {
            border-bottom: none;
        }
        .provider-card:hover, .job-card:hover, .vendor-card:hover {
            background: rgba(245, 175, 25, 0.05);
            margin: 0 -10px;
            padding: 20px 10px;
            border-radius: 16px;
        }
        .provider-info, .job-info, .vendor-info { flex: 1; }

        .profile-pic {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            object-fit: cover;
            border: 3px solid var(--primary);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }
        .vendor-img {
            width: 100px;
            height: 100px;
            object-fit: cover;
            border-radius: 12px;
            border: 1px solid var(--glass-border);
        }

        .badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 0.7rem;
            font-weight: 600;
            margin-left: 8px;
            vertical-align: middle;
        }
        .badge-available { background: #28a745; }
        .badge-occupied { background: #ffc107; color: #333; }
        .badge-leave { background: #6c757d; }
        .badge-open { background: #17a2b8; }
        .badge-taken { background: #6f42c1; }
        .badge-closed { background: #dc3545; }

        .search-bar input {
            width: 100%;
            padding: 14px 20px;
            border-radius: 40px;
            border: 1px solid var(--border);
            background: var(--card-bg);
            color: var(--text);
            font-size: 1rem;
            transition: var(--transition);
        }
        .search-bar input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(245, 175, 25, 0.2);
        }

        label {
            display: block;
            margin-top: 18px;
            margin-bottom: 6px;
            font-weight: 600;
            color: var(--text);
        }
        input, textarea, select {
            width: 100%;
            padding: 12px 16px;
            border-radius: 12px;
            border: 1px solid var(--border);
            background: var(--card-bg);
            color: var(--text);
            font-size: 0.95rem;
            transition: var(--transition);
        }
        input:focus, textarea:focus, select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(245, 175, 25, 0.2);
        }

        .rating {
            color: var(--primary);
            font-size: 1.1rem;
            letter-spacing: 2px;
        }
        .review-card {
            border-left: 3px solid var(--primary);
            padding: 12px 16px;
            margin: 12px 0;
            background: rgba(245, 175, 25, 0.05);
            border-radius: 0 12px 12px 0;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        th {
            font-weight: 700;
            color: var(--primary);
        }

        .whatsapp-float {
            position: fixed;
            bottom: 24px;
            right: 24px;
            background: linear-gradient(135deg, #25D366, #128C7E);
            color: white;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            box-shadow: 0 8px 25px rgba(37, 211, 102, 0.4);
            z-index: 999;
            text-decoration: none;
            transition: var(--transition);
        }
        .whatsapp-float:hover { transform: scale(1.1); }

        footer {
            text-align: center;
            padding: 30px;
            color: var(--text-secondary);
            font-size: 0.85rem;
            border-top: 1px solid var(--border);
            margin-top: 40px;
        }

        .alert {
            padding: 14px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
        }
        .alert-success {
            background: rgba(40, 167, 69, 0.15);
            border: 1px solid rgba(40, 167, 69, 0.3);
            color: #28a745;
        }
        .alert-error {
            background: rgba(220, 53, 69, 0.15);
            border: 1px solid rgba(220, 53, 69, 0.3);
            color: #dc3545;
        }

        .install-btn {
            background: linear-gradient(135deg, #28a745, #20c997);
            color: white;
            border: none;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.85rem;
            cursor: pointer;
            display: none;
            font-weight: 600;
        }
        .install-btn:hover { transform: scale(1.05); }

        /* ================================================
           NEON THEME (Applied via body.theme-neon)
           ================================================ */
        body.theme-neon {
            --primary: #00d4ff !important;
            --primary-dark: #0099cc !important;
            --bg: #0a0a1a !important;
            --card-bg: rgba(20, 20, 40, 0.85) !important;
            --text: #e0e0ff !important;
            --text-secondary: #a0a0cc !important;
            --border: rgba(0, 212, 255, 0.3) !important;
            --shadow: 0 8px 32px rgba(0, 212, 255, 0.2) !important;
            --glass-border: rgba(0, 212, 255, 0.15) !important;
        }

        body.theme-neon {
            background: #0a0a1a !important;
            background-image: 
                radial-gradient(circle at 20% 30%, rgba(0, 212, 255, 0.1) 0%, transparent 50%),
                radial-gradient(circle at 80% 70%, rgba(255, 0, 150, 0.1) 0%, transparent 50%) !important;
        }

        body.theme-neon .hero {
            background: rgba(0, 212, 255, 0.05) !important;
            border: 1px solid rgba(0, 212, 255, 0.2) !important;
        }

        body.theme-neon .hero h1 {
            background: linear-gradient(135deg, #00d4ff, #ff00a0) !important;
            -webkit-background-clip: text !important;
            -webkit-text-fill-color: transparent !important;
            background-clip: text !important;
        }

        body.theme-neon .btn {
            background: linear-gradient(135deg, #00d4ff, #0099cc) !important;
            box-shadow: 0 0 20px rgba(0, 212, 255, 0.4) !important;
        }
        body.theme-neon .btn:hover {
            box-shadow: 0 0 40px rgba(0, 212, 255, 0.6) !important;
            transform: translateY(-2px) !important;
        }
        body.theme-neon .btn-outline {
            border-color: #00d4ff !important;
            color: #00d4ff !important;
        }
        body.theme-neon .btn-outline:hover {
            background: rgba(0, 212, 255, 0.15) !important;
        }

        body.theme-neon .card {
            background: rgba(20, 20, 40, 0.85) !important;
            border: 1px solid rgba(0, 212, 255, 0.2) !important;
        }
        body.theme-neon .card:hover {
            border-color: rgba(0, 212, 255, 0.4) !important;
            box-shadow: 0 0 40px rgba(0, 212, 255, 0.1) !important;
        }
        body.theme-neon .card-header {
            border-bottom-color: rgba(0, 212, 255, 0.2) !important;
        }

        body.theme-neon .stat-card {
            background: rgba(20, 20, 40, 0.7) !important;
            border: 1px solid rgba(0, 212, 255, 0.15) !important;
        }
        body.theme-neon .stat-card h3 {
            color: #00d4ff !important;
        }
        body.theme-neon .stat-card::before {
            background: linear-gradient(135deg, #00d4ff, #ff00a0) !important;
            opacity: 0.2 !important;
        }

        body.theme-neon .navbar {
            background: rgba(20, 20, 40, 0.9) !important;
            border-bottom: 1px solid rgba(0, 212, 255, 0.2) !important;
        }
        body.theme-neon .logo-text span {
            color: #00d4ff !important;
        }
        body.theme-neon .nav-links a:hover,
        body.theme-neon .nav-links a.active {
            background: rgba(0, 212, 255, 0.15) !important;
            color: #00d4ff !important;
        }

        body.theme-neon .chip {
            background: rgba(0, 212, 255, 0.15) !important;
            border-color: rgba(0, 212, 255, 0.2) !important;
        }
        body.theme-neon .chip:hover {
            background: #00d4ff !important;
            color: #0a0a1a !important;
        }

        body.theme-neon .badge-available { 
            background: #00d4ff !important; 
            color: #0a0a1a !important; 
        }
        body.theme-neon .badge-open { 
            background: #00d4ff !important; 
            color: #0a0a1a !important; 
        }
        body.theme-neon .badge-occupied { 
            background: #ff00a0 !important; 
            color: #fff !important; 
        }
        body.theme-neon .badge-closed { 
            background: #ff0040 !important; 
            color: #fff !important; 
        }
        body.theme-neon .badge-taken { 
            background: #ff00a0 !important; 
            color: #fff !important; 
        }
        body.theme-neon .badge-leave { 
            background: #666 !important; 
            color: #fff !important; 
        }

        body.theme-neon .theme-toggle {
            background: rgba(0, 212, 255, 0.15) !important;
            border-color: rgba(0, 212, 255, 0.3) !important;
        }
        body.theme-neon .theme-toggle:hover {
            background: rgba(0, 212, 255, 0.3) !important;
        }

        body.theme-neon .whatsapp-float {
            background: linear-gradient(135deg, #00d4ff, #0099cc) !important;
            box-shadow: 0 0 30px rgba(0, 212, 255, 0.5) !important;
        }
        body.theme-neon .whatsapp-float:hover {
            box-shadow: 0 0 50px rgba(0, 212, 255, 0.7) !important;
        }

        body.theme-neon footer {
            border-top: 1px solid rgba(0, 212, 255, 0.2) !important;
        }

        body.theme-neon .provider-card:hover,
        body.theme-neon .job-card:hover,
        body.theme-neon .vendor-card:hover {
            background: rgba(0, 212, 255, 0.05) !important;
        }

        body.theme-neon input:focus,
        body.theme-neon textarea:focus,
        body.theme-neon select:focus {
            border-color: #00d4ff !important;
            box-shadow: 0 0 0 3px rgba(0, 212, 255, 0.3) !important;
        }
        body.theme-neon input,
        body.theme-neon textarea,
        body.theme-neon select {
            background: rgba(20, 20, 40, 0.6) !important;
            border-color: rgba(0, 212, 255, 0.2) !important;
            color: #e0e0ff !important;
        }

        body.theme-neon th {
            color: #00d4ff !important;
        }
        body.theme-neon td {
            border-bottom-color: rgba(0, 212, 255, 0.1) !important;
        }

        body.theme-neon .alert-success {
            background: rgba(0, 212, 255, 0.1) !important;
            border-color: rgba(0, 212, 255, 0.3) !important;
            color: #00d4ff !important;
        }
        body.theme-neon .alert-error {
            background: rgba(255, 0, 100, 0.1) !important;
            border-color: rgba(255, 0, 100, 0.3) !important;
            color: #ff0064 !important;
        }

        /* ================================================
           RESPONSIVE STYLES
           ================================================ */
        @media (max-width: 768px) {
            .navbar { padding: 12px 16px; }
            .nav-links {
                display: none;
                width: 100%;
                flex-direction: column;
                gap: 10px;
                padding-top: 15px;
            }
            .nav-links.open { display: flex; }
            .hamburger { display: block; }
            .hero h1 { font-size: 1.8rem; }
            .hero { padding: 40px 20px; }
            .provider-card, .job-card, .vendor-card {
                flex-direction: column;
                align-items: flex-start;
            }
            .stat-grid { grid-template-columns: 1fr 1fr; gap: 12px; }
            .container { padding: 0 16px; }
            .card { padding: 20px; }
        }

        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .card, .hero, .stat-card {
            animation: fadeInUp 0.6s ease-out;
        }
    </style>
</head>
<body>
    <nav class="navbar">
        <a href="/" class="logo">
            <img src="/static/pngwing.com.png" alt="RockabyConnect Logo">
            <div>
                <div class="logo-text">ROCKABY<span>CONNECT</span></div>
                <div class="logo-sub">Connecting Skills, Building Uganda</div>
            </div>
        </a>
        <button class="hamburger" onclick="toggleMenu()">☰</button>
        <div class="nav-links" id="navMenu">
            <a href="/" class="{{ 'active' if active_page == 'home' else '' }}">Home</a>
            {% if session.user_id %}
                <a href="/dashboard" class="{{ 'active' if active_page == 'dashboard' else '' }}">Dashboard</a>
            {% endif %}
            <a href="/list" class="{{ 'active' if active_page == 'list' else '' }}">Find Skills</a>
            <a href="/jobs" class="{{ 'active' if active_page == 'jobs' else '' }}">Jobs</a>
            <a href="/vendors" class="{{ 'active' if active_page == 'vendors' else '' }}">Vendors</a>
            {% if session.user_id %}
                <a href="/my-applications" class="{{ 'active' if active_page == 'applications' else '' }}">📋 My Applications</a>
                <!-- ===== MESSAGES LINK WITH UNREAD BADGE ===== -->
                <a href="/messages" id="messagesLink">📨 Messages <span id="messagesBadge" class="badge" style="background:#dc3545; color:white; display:none;"></span></a>
                <!-- ===== NOTIFICATION BELL ===== -->
                <a href="/notifications" id="notifLink">🔔 <span id="notifBadge" class="badge" style="background:#dc3545; color:white; display:none;"></span></a>
                <!-- ===== END NOTIFICATION ===== -->
                <a href="/refer" class="{{ 'active' if active_page == 'refer' else '' }}">🎁 Refer</a>
                <a href="/settings" class="{{ 'active' if active_page == 'settings' else '' }}">⚙️ Settings</a>
                <a href="/logout">Logout</a>
            {% else %}
                <a href="/login" class="{{ 'active' if active_page == 'login' else '' }}">Login</a>
                <a href="/signup" class="{{ 'active' if active_page == 'signup' else '' }}">Sign Up</a>
            {% endif %}
            <button class="theme-toggle" onclick="toggleTheme()" title="Toggle Dark/Light Mode">🌓</button>
            <button id="installBtn" class="install-btn"><i class="fas fa-download"></i> Install App</button>
        </div>
    </nav>
    <div class="container">
        {content}
    </div>
    <footer>&copy; 2025 RockabyTech – Connecting Skills, Building Uganda 🇺🇬</footer>
    <a href="https://wa.me/256751318876?text=Hi%20RockabyConnect%20Support" target="_blank" class="whatsapp-float">💬</a>
    <script>
        function toggleMenu() {
            document.getElementById('navMenu').classList.toggle('open');
        }
        function toggleTheme() {
            document.body.classList.toggle('dark-mode');
            const theme = document.body.classList.contains('dark-mode') ? 'dark' : 'light';
            localStorage.setItem('rockabyconnect-theme', theme);
        }
        const savedTheme = localStorage.getItem('rockabyconnect-theme');
        if (savedTheme === 'dark') {
            document.body.classList.add('dark-mode');
        }

        // PWA install prompt
        let deferredPrompt;
        const installBtn = document.getElementById('installBtn');

        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPrompt = e;
            installBtn.style.display = 'inline-block';
        });

        installBtn.addEventListener('click', async () => {
            if (deferredPrompt) {
                deferredPrompt.prompt();
                const { outcome } = await deferredPrompt.userChoice;
                deferredPrompt = null;
                installBtn.style.display = 'none';
            }
        });

        window.addEventListener('appinstalled', () => {
            installBtn.style.display = 'none';
        });

        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/service-worker.js')
                    .then(() => console.log('Service Worker registered'))
                    .catch(err => console.log('Service Worker failed:', err));
            });
        }

        // ===== CLIENT-SIDE IMAGE COMPRESSION =====
        document.addEventListener('DOMContentLoaded', function() {
            const forms = document.querySelectorAll('form');
            forms.forEach(form => {
                const fileInputs = form.querySelectorAll('input[type="file"][accept*="image/"]');
                if (fileInputs.length === 0) return;

                form.addEventListener('submit', function(e) {
                    let hasLargeFile = false;
                    const promises = [];

                    fileInputs.forEach(input => {
                        if (input.files.length > 0) {
                            const file = input.files[0];
                            if (file.size > 1 * 1024 * 1024) {
                                hasLargeFile = true;
                                promises.push(new Promise((resolve) => {
                                    compressImage(file, function(compressedFile) {
                                        const dt = new DataTransfer();
                                        dt.items.add(compressedFile);
                                        input.files = dt.files;
                                        resolve();
                                    });
                                }));
                            }
                        }
                    });

                    if (hasLargeFile) {
                        e.preventDefault();
                        Promise.all(promises).then(() => {
                            form.submit();
                        });
                    }
                });
            });
        });

        function compressImage(file, callback) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const img = new Image();
                img.onload = function() {
                    const canvas = document.createElement('canvas');
                    const MAX_WIDTH = 1200;
                    const MAX_HEIGHT = 1200;
                    let width = img.width;
                    let height = img.height;

                    if (width > height) {
                        if (width > MAX_WIDTH) {
                            height = Math.round(height * MAX_WIDTH / width);
                            width = MAX_WIDTH;
                        }
                    } else {
                        if (height > MAX_HEIGHT) {
                            width = Math.round(width * MAX_HEIGHT / height);
                            height = MAX_HEIGHT;
                        }
                    }

                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, width, height);
                    canvas.toBlob(function(blob) {
                        const compressedFile = new File([blob], file.name, {
                            type: 'image/jpeg',
                            lastModified: Date.now()
                        });
                        callback(compressedFile);
                    }, 'image/jpeg', 0.85);
                };
                img.src = e.target.result;
            };
            reader.readAsDataURL(file);
        }

        // ============================================================
        // UNREAD NOTIFICATIONS BADGE
        // ============================================================
        function updateNotifBadge() {
            fetch('/api/unread-notifications')
                .then(r => r.json())
                .then(data => {
                    const badge = document.getElementById('notifBadge');
                    if (badge) {
                        if (data.count > 0) {
                            badge.textContent = data.count;
                            badge.style.display = 'inline-block';
                        } else {
                            badge.style.display = 'none';
                        }
                    }
                })
                .catch(err => console.log('Error fetching unread count:', err));
        }

        // ============================================================
        // UNREAD MESSAGES BADGE
        // ============================================================
        function updateUnreadBadge() {
            fetch('/api/unread-count')
                .then(r => r.json())
                .then(data => {
                    const badge = document.getElementById('messagesBadge');
                    if (badge) {
                        if (data.count > 0) {
                            badge.textContent = data.count;
                            badge.style.display = 'inline-block';
                        } else {
                            badge.style.display = 'none';
                        }
                    }
                })
                .catch(err => console.log('Error fetching unread count:', err));
        }

        // ============================================================
        // INITIALISE AND POLL
        // ============================================================
        if (document.getElementById('messagesBadge')) {
            updateUnreadBadge();
            setInterval(updateUnreadBadge, 15000);
        }

        if (document.getElementById('notifBadge')) {
            updateNotifBadge();
            setInterval(updateNotifBadge, 15000);
        }
    </script>
</body>
</html>
"""

# ============================================================
# ADMIN BASE TEMPLATE (Glassmorphism + Dark Mode)
# ============================================================
admin_base_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>RockabyConnect Admin – {title}</title>
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#f5af19">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --primary: #f5af19;
            --primary-dark: #e09e15;
            --primary-light: #f7c35c;
            --secondary: #1a73e8;
            --bg: #f0f4f8;
            --card-bg: rgba(255, 255, 255, 0.85);
            --glass-border: rgba(255, 255, 255, 0.3);
            --text: #1a1a1a;
            --text-secondary: #666;
            --border: #e0e0e0;
            --radius: 20px;
            --shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
            --shadow-hover: 0 12px 48px rgba(0, 0, 0, 0.12);
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        body.dark-mode {
            --bg: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.85);
            --glass-border: rgba(255, 255, 255, 0.08);
            --text: #f1f5f9;
            --text-secondary: #94a3b8;
            --border: #334155;
            --shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(245, 175, 25, 0.08) 0%, transparent 50%),
                radial-gradient(circle at 90% 80%, rgba(26, 115, 232, 0.08) 0%, transparent 50%);
            color: var(--text);
            min-height: 100vh;
            transition: var(--transition);
        }

        .navbar {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-bottom: 1px solid var(--glass-border);
            padding: 16px 24px;
            position: sticky;
            top: 0;
            z-index: 1000;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 15px;
        }

        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
        }

        .logo img {
            height: 45px;
            width: 45px;
            border-radius: 12px;
            object-fit: cover;
            box-shadow: 0 4px 15px rgba(245, 175, 25, 0.3);
        }

        .logo-text {
            font-size: 1.3rem;
            font-weight: 800;
            line-height: 1.2;
        }
        .logo-text span { color: var(--primary); }
        .logo-sub {
            font-size: 0.7rem;
            color: var(--text-secondary);
            line-height: 1;
        }

        .nav-links {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            align-items: center;
        }
        .nav-links a {
            color: var(--text-secondary);
            text-decoration: none;
            font-weight: 500;
            padding: 8px 16px;
            border-radius: 12px;
            transition: var(--transition);
            font-size: 0.95rem;
        }
        .nav-links a:hover,
        .nav-links a.active {
            background: rgba(245, 175, 25, 0.15);
            color: var(--primary);
        }

        .theme-toggle {
            background: rgba(245, 175, 25, 0.1);
            border: 1px solid var(--glass-border);
            border-radius: 50%;
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 1.2rem;
            transition: var(--transition);
            color: var(--text);
        }
        .theme-toggle:hover {
            background: rgba(245, 175, 25, 0.2);
            transform: scale(1.05);
        }

        .hamburger {
            display: none;
            background: none;
            border: none;
            font-size: 1.8rem;
            cursor: pointer;
            color: var(--text);
        }

        .container {
            max-width: 1200px;
            margin: 24px auto;
            padding: 0 20px;
        }

        .card {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border-radius: var(--radius);
            padding: 28px;
            margin-bottom: 24px;
            box-shadow: var(--shadow);
            border: 1px solid var(--glass-border);
            transition: var(--transition);
        }
        .card:hover {
            transform: translateY(-4px);
            box-shadow: var(--shadow-hover);
        }
        .card-header {
            font-size: 1.3rem;
            font-weight: 700;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 2px solid var(--primary);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .btn {
            display: inline-block;
            padding: 12px 28px;
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: white;
            border: none;
            border-radius: 12px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            font-size: 0.95rem;
            transition: var(--transition);
            box-shadow: 0 4px 15px rgba(245, 175, 25, 0.3);
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(245, 175, 25, 0.4);
        }
        .btn-outline {
            background: transparent;
            border: 2px solid var(--primary);
            color: var(--primary);
            box-shadow: none;
        }
        .btn-outline:hover {
            background: rgba(245, 175, 25, 0.1);
        }
        .btn-danger {
            background: linear-gradient(135deg, #dc3545, #c82333);
        }
        .btn-small {
            padding: 6px 14px;
            font-size: 0.85rem;
        }

        .stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border-radius: var(--radius);
            padding: 28px 20px;
            text-align: center;
            border: 1px solid var(--glass-border);
            transition: var(--transition);
            position: relative;
            overflow: hidden;
        }
        .stat-card::before {
            content: '';
            position: absolute;
            top: -30px;
            right: -30px;
            width: 80px;
            height: 80px;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            opacity: 0.1;
            border-radius: 50%;
        }
        .stat-card h3 {
            font-size: 2.5rem;
            font-weight: 800;
            color: var(--primary);
            margin-bottom: 8px;
        }
        .stat-card small {
            color: var(--text-secondary);
            font-size: 0.9rem;
        }

        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        th {
            font-weight: 700;
            color: var(--primary);
        }

        .alert {
            padding: 14px 20px;
            border-radius: 12px;
            margin-bottom: 20px;
        }
        .alert-success {
            background: rgba(40, 167, 69, 0.15);
            border: 1px solid rgba(40, 167, 69, 0.3);
            color: #28a745;
        }
        .alert-error {
            background: rgba(220, 53, 69, 0.15);
            border: 1px solid rgba(220, 53, 69, 0.3);
            color: #dc3545;
        }

        footer {
            text-align: center;
            padding: 30px;
            color: var(--text-secondary);
            font-size: 0.85rem;
            border-top: 1px solid var(--border);
            margin-top: 40px;
        }

        @media (max-width: 768px) {
            .navbar { padding: 12px 16px; }
            .nav-links {
                display: none;
                width: 100%;
                flex-direction: column;
                gap: 10px;
                padding-top: 15px;
            }
            .nav-links.open { display: flex; }
            .hamburger { display: block; }
            .stat-grid { grid-template-columns: 1fr 1fr; gap: 12px; }
            .container { padding: 0 16px; }
            .card { padding: 20px; }
        }

        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .card, .stat-card {
            animation: fadeInUp 0.6s ease-out;
        }
    </style>
</head>
<body class="{theme_class}">
    <nav class="navbar">
        <a href="/admin/dashboard" class="logo">
            <img src="/static/pngwing.com.png" alt="RockabyConnect Logo">
            <div>
                <div class="logo-text">ROCKABY<span>CONNECT</span></div>
                <div class="logo-sub">Admin Panel</div>
            </div>
        </a>
        <button class="hamburger" onclick="toggleMenu()">☰</button>
        <div class="nav-links" id="navMenu">
            <a href="/admin/dashboard" class="{{ 'active' if active_page == 'dashboard' else '' }}">Dashboard</a>
            <a href="/admin/stats" class="{{ 'active' if active_page == 'stats' else '' }}">Statistics</a>
            <a href="/admin/backups" class="{{ 'active' if active_page == 'backups' else '' }}">Backups</a>
            <a href="/admin/logout">Logout</a>
            <button class="theme-toggle" onclick="toggleTheme()" title="Toggle Dark/Light Mode">🌓</button>
        </div>
    </nav>
    <div class="container">
        {content}
    </div>
    <footer>&copy; 2025 RockabyTech – Admin Panel</footer>
    <script>
        function toggleMenu() {
            document.getElementById('navMenu').classList.toggle('open');
        }
        function toggleTheme() {
            document.body.classList.toggle('dark-mode');
            const theme = document.body.classList.contains('dark-mode') ? 'dark' : 'light';
            localStorage.setItem('rockabyconnect-admin-theme', theme);
        }
        const savedTheme = localStorage.getItem('rockabyconnect-admin-theme');
        if (savedTheme === 'dark') {
            document.body.classList.add('dark-mode');
        }
    </script>
</body>
</html>
"""

# ============================================================
# PAGE FRAGMENTS (Unchanged from your PythonAnywhere code)
# ============================================================
home_page = base_template.replace("{title}", "Home").replace("{active_page}", "home").replace("{content}", """
    <div class="hero">
        <div style="display:flex; align-items:center; justify-content:center; gap:20px; flex-wrap:wrap; margin-bottom:15px;">
            <img src="/static/ug-06.png" alt="RockabyConnect Logo" style="height:80px; width:80px; border-radius:16px; object-fit:cover; box-shadow:0 4px 15px rgba(0,0,0,0.2);">
            <h1 style="margin:0;">Get Work Done – or Get Paid</h1>
        </div>
        <p>Uganda's premier freelance marketplace. Connect with trusted skilled workers near you.</p>
        <div style="display: flex; gap: 15px; justify-content: center; flex-wrap: wrap;">
            <a href="/offer-skill" class="btn" style="border-color:white; color:white; background:var(--primary);">Offer Your Skill</a>
            <a href="/post-job" class="btn btn-outline" style="border-color:white; color:white;">Post a Job</a>
        </div>
        <div class="category-chips">
            <span style="color: var(--text-secondary);">Popular:</span>
            <a href="/list?search=Boda+Rider" class="chip">Boda Rider</a>
            <a href="/list?search=Maid" class="chip">Maid</a>
            <a href="/list?search=Plumbing" class="chip">Plumbing</a>
            <a href="/list?search=Electrical" class="chip">Electrical</a>
            <a href="/list?search=Carpentry" class="chip">Carpentry</a>
            <a href="/list?search=Cooking" class="chip">Cooking</a>
            <a href="/list?search=Driver" class="chip">Driver</a>
        </div>
    </div>
    <div class="stat-grid">
        <div class="stat-card"><h3>{provider_count}</h3><small>Skilled Workers</small></div>
        <div class="stat-card"><h3>{open_jobs}</h3><small>Open Jobs</small></div>
        <div class="stat-card"><h3>10K+</h3><small>Monthly Visitors</small></div>
    </div>
    <div class="card">
        <div class="card-header">📖 How It Works</div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; text-align: center;">
            <div><div style="font-size: 2rem;">🔍</div><h3>1. Find Skills</h3><p>Browse verified workers</p></div>
            <div><div style="font-size: 2rem;">📝</div><h3>2. Post a Job</h3><p>Describe what you need</p></div>
            <div><div style="font-size: 2rem;">💬</div><h3>3. Connect</h3><p>Chat on WhatsApp</p></div>
        </div>
    </div>
""")
signup_page = base_template.replace("{title}", "Sign Up").replace("{active_page}", "signup").replace("{content}", """
    <div class="card">
        <div class="card-header">Create Your Free Account</div>
        <form method="POST">
            <label>Full Name *</label>
            <input type="text" name="name" required>
            <label>Phone Number *</label>
            <input type="tel" name="phone" required>
            <label>Password *</label>
            <input type="password" name="password" required>
            <button type="submit" class="btn" style="margin-top:20px; width:100%;">Sign Up</button>
        </form>
        <p style="margin-top:15px;">Already have an account? <a href="/login">Login</a></p>
    </div>
""")

login_page = base_template.replace("{title}", "Login").replace("{active_page}", "login").replace("{content}", """
    <div class="card">
        <div class="card-header">Login</div>
        <form method="POST">
            <label>Phone Number</label>
            <input type="tel" name="phone" required>
            <label>Password</label>
            <input type="password" name="password" required>
            <button type="submit" class="btn" style="margin-top:20px; width:100%;">Login</button>
        </form>
        <p style="margin-top:15px;">No account? <a href="/signup">Sign Up</a></p>
    </div>
""")

dashboard_template = base_template.replace("{title}", "Dashboard").replace("{active_page}", "dashboard").replace("{content}", """
    <div class="card">
        <div class="card-header">Welcome, {session['user_name']}!</div>
        <p style="color:var(--text-secondary);"><a href="/edit-name" style="font-size:0.85rem; color:var(--primary-dark);">Edit my name</a></p>
        <p style="color:#666;">Manage your freelance presence, vendor profile, and job postings.</p>
        <div style="display:flex; gap:10px; margin-top:15px; flex-wrap:wrap;">
            <a href="/settings" class="btn btn-small" style="background:var(--primary-dark);">⚙️ Settings</a>
            <a href="/refer" class="btn btn-small" style="background:var(--primary);">🎁 Refer a Friend</a>
            <a href="/my-applications" class="btn btn-small" style="background:#17a2b8;">📋 My Applications</a>
            <a href="/messages" class="btn btn-small" style="background:#28a745;">📨 Messages</a>
        </div>
        <div style="margin-top:15px; padding:15px; background:linear-gradient(135deg, rgba(245,175,25,0.1), rgba(245,175,25,0.05)); border-radius:12px; border:1px solid var(--glass-border);">
            <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
                <span style="font-size:1.8rem;">🎁</span>
                <div style="flex:1;">
                    <h4 style="margin:0;">Refer a Friend & Earn Rewards!</h4>
                    <p style="margin:0; font-size:0.9rem; color:var(--text-secondary);">Share your referral link and earn rewards when your friends sign up.</p>
                </div>
                <a href="/refer" class="btn" style="background:var(--primary-dark); white-space:nowrap;">
                    <i class="fas fa-share-alt"></i> Refer Now
                </a>
            </div>
        </div>
    </div>
    {profile_section}
    {vendor_section}
    <div class="card">
        <div class="card-header">My Job Postings</div>
        {jobs_html}
        <a href="/post-job" class="btn" style="margin-top:10px;">Post a New Job</a>
    </div>
""")

profile_form_template = base_template.replace("{title}", "My Freelancer Profile").replace("{content}", """
    <div class="card">
        <div class="card-header">{form_title}</div>
        <form method="POST" enctype="multipart/form-data">
            <label>Skills * (separate by commas)</label>
            <input type="text" name="skills" value="{skills}" required placeholder="e.g., Plumbing, Boda Rider, Carpentry">
            <p style="font-size:0.8rem;">Suggestions: {skill_suggestions}</p>
            <label>District/City *</label>
            <input type="text" name="district" value="{district}" required>
            <label>Village/Area</label>
            <input type="text" name="village" value="{village}">
            <label>Short Bio</label>
            <textarea name="bio" maxlength="300">{bio}</textarea>
            <label>Profile Picture</label>
            <input type="file" name="profile_pic" accept="image/*">
            <p style="font-size:0.8rem;">Leave blank to keep current picture.</p>
            <!-- ===== VIDEO UPLOAD ===== -->
            <label>Upload a Video (optional)</label>
            <input type="file" name="video" accept="video/*">
            <p style="font-size:0.8rem;">MP4, WebM, OGG, MOV, AVI, MKV (max 50MB recommended)</p>
            <!-- ===== END VIDEO ===== -->
            <label>Availability Status</label>
            <select name="status">
                {status_options}
            </select>
            <button type="submit" class="btn" style="margin-top:20px; width:100%;">Save Profile</button>
        </form>
    </div>
""")

vendor_form_template = base_template.replace("{title}", "My Vendor Profile").replace("{content}", """
    <div class="card">
        <div class="card-header">{form_title}</div>
        <form method="POST" enctype="multipart/form-data" id="vendorForm">
            <label>Business Name *</label>
            <input type="text" name="business_name" value="{business_name}" required>
            <label>District/City *</label>
            <input type="text" name="district" value="{district}" required>
            <label>Village/Area</label>
            <input type="text" name="village" value="{village}">
            <label>Landmark (e.g., opp. SDA church, Mukwano B23)</label>
            <input type="text" name="landmark" value="{landmark}">
            <label>Short Description</label>
            <textarea name="bio" maxlength="300">{bio}</textarea>
            <label>Main Shop / Product Photo</label>
            <input type="file" name="vendor_image" accept="image/*">
            <label>Additional Photo 1</label>
            <input type="file" name="vendor_image2" accept="image/*">
            <label>Additional Photo 2</label>
            <input type="file" name="vendor_image3" accept="image/*">
            <!-- ===== VIDEO UPLOAD ===== -->
            <label>Upload a Video (optional)</label>
            <input type="file" name="video" accept="video/*">
            <p style="font-size:0.8rem;">MP4, WebM, OGG, MOV, AVI, MKV (max 50MB recommended)</p>
            <!-- ===== END VIDEO ===== -->
            <label>Status</label>
            <select name="status">
                {status_options}
            </select>
            <button type="submit" class="btn" style="margin-top:20px; width:100%;">Save Vendor Profile</button>
        </form>
    </div>
    <script>
    // Client-side image resizer – compresses images before upload for lightning speed
    document.getElementById('vendorForm').addEventListener('submit', function(e) {
        const fileInputs = document.querySelectorAll('#vendorForm input[type=file]');
        const promises = [];
        fileInputs.forEach(input => {
            if (input.files.length > 0) {
                const file = input.files[0];
                if (file.size > 500 * 1024) { // only resize if > 500KB
                    promises.push(new Promise((resolve) => {
                        const reader = new FileReader();
                        reader.onload = function(ev) {
                            const img = new Image();
                            img.onload = function() {
                                const canvas = document.createElement('canvas');
                                const maxWidth = 800;
                                let width = img.width, height = img.height;
                                if (width > maxWidth) {
                                    height = Math.round((maxWidth / width) * height);
                                    width = maxWidth;
                                }
                                canvas.width = width;
                                canvas.height = height;
                                const ctx = canvas.getContext('2d');
                                ctx.drawImage(img, 0, 0, width, height);
                                canvas.toBlob(function(blob) {
                                    const resizedFile = new File([blob], file.name, { type: 'image/jpeg', lastModified: Date.now() });
                                    const dt = new DataTransfer();
                                    dt.items.add(resizedFile);
                                    input.files = dt.files;
                                    resolve();
                                }, 'image/jpeg', 0.85);
                            };
                            img.src = ev.target.result;
                        };
                        reader.readAsDataURL(file);
                    }));
                }
            }
        });
        if (promises.length > 0) {
            e.preventDefault();
            Promise.all(promises).then(() => {
                document.getElementById('vendorForm').submit();
            });
        }
    });
    </script>
""")

job_form_template = base_template.replace("{title}", "{job_form_title}").replace("{content}", """
    <div class="card">
        <div class="card-header">{form_header}</div>
        <form method="POST" enctype="multipart/form-data">
            <label>Job Title *</label>
            <input type="text" name="title" value="{title_val}" required>
            <label>Company / Your Name</label>
            <input type="text" name="company" value="{company_val}">
            <label>Description *</label>
            <textarea name="description" rows="4" required>{description_val}</textarea>
            <label>District/City *</label>
            <input type="text" name="location" value="{location_val}" required>
            <label>Village/Area</label>
            <input type="text" name="village" value="{village_val}">
            <label>Contact (phone or email)</label>
            <input type="text" name="contact" value="{contact_val}">
            <label>Job Image (optional)</label>
            <input type="file" name="job_image" accept="image/*">
            <!-- ===== VIDEO UPLOAD ===== -->
            <label>Upload a Video (optional)</label>
            <input type="file" name="video" accept="video/*">
            <p style="font-size:0.8rem;">MP4, WebM, OGG, MOV, AVI, MKV (max 50MB recommended)</p>
            <!-- ===== END VIDEO ===== -->
            <button type="submit" class="btn" style="margin-top:20px; width:100%;">{submit_button}</button>
        </form>
    </div>
""")

list_page = base_template.replace("{title}", "Find Skills").replace("{active_page}", "list").replace("{content}", """
    <div class="card">
        <div class="card-header">Skill Providers</div>
        <div class="search-bar"><input type="text" id="searchInput" placeholder="Filter by skill, district, village..." onkeyup="filterCards()"></div>
        <div id="providerCards">{cards}</div>
    </div>
    <script>
        function filterCards() {
            const q = document.getElementById('searchInput').value.toLowerCase();
            document.querySelectorAll('.provider-card').forEach(card => {
                card.style.display = card.innerText.toLowerCase().includes(q) ? 'flex' : 'none';
            });
        }
    </script>
""")

job_list_page = base_template.replace("{title}", "Jobs").replace("{active_page}", "jobs").replace("{content}", """
    <div class="card">
        <div class="card-header">Available Jobs</div>
        <div class="search-bar">
            <input type="text" id="jobSearch" placeholder="Search by title, location..." onkeyup="filterJobs()">
        </div>
        <div style="display:flex; gap:10px; margin-bottom:15px;">
            <select id="statusFilter" onchange="filterJobs()">
                <option value="">All Statuses</option>
                <option value="open">Open</option>
                <option value="taken">Taken</option>
                <option value="closed">Closed</option>
            </select>
            <input type="text" id="locationFilter" placeholder="Filter by location" onkeyup="filterJobs()" style="max-width:200px;">
        </div>
        <div id="jobCards">{jobs_html}</div>
    </div>
    <script>
        function filterJobs() {
            const q = document.getElementById('jobSearch').value.toLowerCase();
            const status = document.getElementById('statusFilter').value.toLowerCase();
            const loc = document.getElementById('locationFilter').value.toLowerCase();
            document.querySelectorAll('.job-card').forEach(card => {
                const text = card.innerText.toLowerCase();
                const matchesSearch = q === '' || text.includes(q);
                const matchesStatus = status === '' || text.includes('badge-' + status);
                const matchesLoc = loc === '' || text.includes(loc);
                card.style.display = matchesSearch && matchesStatus && matchesLoc ? 'flex' : 'none';
            });
        }
    </script>
""")

vendor_list_page = base_template.replace("{title}", "Vendors").replace("{active_page}", "vendors").replace("{content}", """
    <div class="card">
        <div class="card-header">Local Vendors & Shops</div>
        <div class="search-bar"><input type="text" id="vendorSearch" placeholder="Search by business name, location, landmark..." onkeyup="filterVendors()"></div>
        <div id="vendorCards">{cards}</div>
    </div>
    <script>
        function filterVendors() {
            const q = document.getElementById('vendorSearch').value.toLowerCase();
            document.querySelectorAll('.vendor-card').forEach(card => {
                card.style.display = card.innerText.toLowerCase().includes(q) ? 'flex' : 'none';
            });
        }
    </script>
""")

vendor_detail_template = base_template.replace("{title}", "Vendor Detail").replace("{active_page}", "vendors").replace("{content}", """
    <div class="card">
        <div class="card-header">{business_name}</div>
        <img src="{img_url}" class="vendor-img" style="width:100%; max-height:300px; object-fit:cover; border-radius:8px; margin-bottom:15px;">
        {extra_images}
        <!-- ===== VIDEO DISPLAY ===== -->
        {video_display}
        <!-- ===== END VIDEO ===== -->
        <p><strong>Location:</strong> {district}{village_display}{landmark_display}</p>
        <p><strong>Description:</strong> {bio}</p>
        <p><strong>Status:</strong> <span class="badge badge-{status_class}">{status}</span> {feat}</p>
        {contact_display}
    </div>
""")

provider_detail_template = base_template.replace("{title}", "Provider Detail").replace("{active_page}", "list").replace("{content}", """
    <div class="card">
        <div class="card-header">{provider_name}</div>
        <img src="{img_url}" class="profile-pic" style="width:120px; height:120px; margin-bottom:15px;">
        <!-- ===== VIDEO DISPLAY ===== -->
        {video_display}
        <!-- ===== END VIDEO ===== -->
        <p><strong>Skills:</strong> {skills}</p>
        <p><strong>Location:</strong> {district}{village_display}</p>
        <p><strong>Bio:</strong> {bio}</p>
        <p><strong>Status:</strong> <span class="badge badge-{status_class}">{status}</span> {feat}</p>
        {contact_display}
        <hr>
        <h3>Reviews ({avg_rating}/5)</h3>
        <div id="reviews">{reviews_html}</div>
        {review_form}
    </div>
""")

edit_name_page = base_template.replace("{title}", "Edit Name").replace("{content}", """
    <div class="card">
        <div class="card-header">Edit Your Name</div>
        <form method="POST" action="/update-name">
            <label>Full Name *</label>
            <input type="text" name="name" value="{current_name}" required>
            <button type="submit" class="btn" style="margin-top:20px;">Update Name</button>
        </form>
    </div>
""")

# ============================================================
# CUSTOMER ROUTES (FULL SET)
# ============================================================

@app.route('/')
def home():
    # ---- REFERRAL CODE DETECTION ----
    ref_code = request.args.get('ref', '')
    if ref_code:
        session['referral_code'] = ref_code
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM providers")
    provider_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM jobs WHERE status='Open'")
    open_jobs = c.fetchone()[0]
    
    # ---- FETCH BOOSTED ITEMS (Ad carousel) ----
    today = date.today().isoformat()
    ads = []
    # Providers
    c.execute("""
        SELECT p.id, u.name, p.profile_pic, p.video, p.featured_expiry, 'provider' as type
        FROM providers p JOIN users u ON p.user_id = u.id
        WHERE p.featured = 1 AND (p.featured_expiry IS NULL OR p.featured_expiry >= ?)
    """, (today,))
    for row in c.fetchall():
        ads.append({'id': row[0], 'name': row[1], 'image': row[2], 'video': row[3], 'type': row[5]})
    # Vendors
    c.execute("""
        SELECT v.id, v.business_name, v.vendor_image, v.video, v.featured_expiry, 'vendor' as type
        FROM vendors v
        WHERE v.featured = 1 AND (v.featured_expiry IS NULL OR v.featured_expiry >= ?)
    """, (today,))
    for row in c.fetchall():
        ads.append({'id': row[0], 'name': row[1], 'image': row[2], 'video': row[3], 'type': row[5]})
    # Jobs
    c.execute("""
        SELECT j.id, j.title, j.job_image, j.video, j.featured_expiry, 'job' as type
        FROM jobs j
        WHERE j.featured = 1 AND (j.featured_expiry IS NULL OR j.featured_expiry >= ?)
    """, (today,))
    for row in c.fetchall():
        ads.append({'id': row[0], 'name': row[1], 'image': row[2], 'video': row[3], 'type': row[5]})
    conn.close()

    # ---- Build carousel HTML ----
    carousel_html = ""
    if ads:
        carousel_html = """
        <div class="ad-carousel" style="position:relative; overflow:hidden; border-radius:var(--radius); margin-bottom:30px; background:#000; min-height:200px;">
            <div class="carousel-track" style="display:flex; transition: transform 0.5s ease;">
        """
        for ad in ads:
            media = ""
            if ad['video']:
                media = f'<video src="/static/uploads/{ad["video"]}" autoplay muted loop playsinline style="width:100%; max-height:400px; object-fit:cover;"></video>'
            elif ad['image']:
                media = f'<img src="/static/uploads/{ad["image"]}" alt="{ad["name"]}" style="width:100%; max-height:400px; object-fit:cover;">'
            else:
                media = f'<div style="width:100%; max-height:400px; background:var(--primary); display:flex; align-items:center; justify-content:center; color:white; font-size:1.5rem;">{ad["name"]}</div>'
            label = f'<div style="position:absolute; bottom:10px; left:10px; background:rgba(0,0,0,0.6); color:white; padding:4px 12px; border-radius:20px; font-size:0.8rem;">{ad["type"].title()}</div>'
            carousel_html += f"""
                <div class="carousel-slide" style="min-width:100%; position:relative;">
                    {media}
                    {label}
                </div>
            """
        carousel_html += """
            </div>
            <button class="carousel-prev" style="position:absolute; left:10px; top:50%; transform:translateY(-50%); background:rgba(0,0,0,0.5); color:white; border:none; border-radius:50%; width:40px; height:40px; cursor:pointer; z-index:2; font-size:1.5rem;">‹</button>
            <button class="carousel-next" style="position:absolute; right:10px; top:50%; transform:translateY(-50%); background:rgba(0,0,0,0.5); color:white; border:none; border-radius:50%; width:40px; height:40px; cursor:pointer; z-index:2; font-size:1.5rem;">›</button>
            <div class="carousel-dots" style="position:absolute; bottom:10px; left:50%; transform:translateX(-50%); display:flex; gap:8px; z-index:2;"></div>
        </div>
        <script>
            (function() {
                const track = document.querySelector('.carousel-track');
                const slides = track.querySelectorAll('.carousel-slide');
                const prev = document.querySelector('.carousel-prev');
                const next = document.querySelector('.carousel-next');
                const dotsContainer = document.querySelector('.carousel-dots');
                let current = 0;
                const total = slides.length;
                let interval;

                for (let i = 0; i < total; i++) {
                    const dot = document.createElement('span');
                    dot.style.width = '10px';
                    dot.style.height = '10px';
                    dot.style.borderRadius = '50%';
                    dot.style.background = i === 0 ? 'white' : 'rgba(255,255,255,0.4)';
                    dot.style.cursor = 'pointer';
                    dot.dataset.index = i;
                    dot.addEventListener('click', () => goTo(i));
                    dotsContainer.appendChild(dot);
                }
                const dots = dotsContainer.querySelectorAll('span');

                function goTo(index) {
                    current = (index + total) % total;
                    track.style.transform = `translateX(-${current * 100}%)`;
                    dots.forEach((d, i) => d.style.background = i === current ? 'white' : 'rgba(255,255,255,0.4)');
                }

                function nextSlide() { goTo(current + 1); }
                function prevSlide() { goTo(current - 1); }

                next.addEventListener('click', () => { clearInterval(interval); nextSlide(); startAutoPlay(); });
                prev.addEventListener('click', () => { clearInterval(interval); prevSlide(); startAutoPlay(); });

                function startAutoPlay() {
                    interval = setInterval(nextSlide, 5000);
                }
                startAutoPlay();

                const carousel = document.querySelector('.ad-carousel');
                carousel.addEventListener('mouseenter', () => clearInterval(interval));
                carousel.addEventListener('mouseleave', startAutoPlay);
            })();
        </script>
        """
    
    # ---- Prepare page content ----
    content = home_page.replace("{provider_count}", str(provider_count)).replace("{open_jobs}", str(open_jobs))
    # Insert carousel after hero
    if '{carousel}' in content:
        content = content.replace("{carousel}", carousel_html)
    else:
        # If no placeholder, insert after hero
        hero_end = content.find('</div>', content.find('class="hero"')) + 6
        content = content[:hero_end] + carousel_html + content[hero_end:]

    return render_user_template(content, title="Home", active_page="home")

# ============================================================
# NOTIFICATION API & PAGE
# ============================================================

@app.route('/api/unread-notifications')
@login_required
def api_unread_notifications():
    count = get_unread_notifications(session['user_id'])
    return {'count': count}

@app.route('/notifications')
@login_required
def notifications():
    user_id = session['user_id']
    # Mark all as read when viewing the page
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

    notifs = get_notifications(user_id, 50)
    rows = ""
    for n in notifs:
        nid, ntype, msg, link, is_read, created_at = n
        icon = {
    'job_application': '📋',
    'application_status': '🔄',
    'application_note': '📝',  # <-- ADD THIS
    'message': '💬',
    'boost_approved': '⭐',
    'boost_rejected': '❌'
}.get(ntype, '🔔')
        link_html = f'<a href="{link}" class="btn btn-small">View</a>' if link else ''
        rows += f"""
        <div class="provider-card">
            <div class="provider-info">
                <h3>{icon} {msg}</h3>
                <small>{created_at[:16]}</small>
                {link_html}
            </div>
        </div>
        """
    if not rows:
        rows = "<p>No notifications yet.</p>"

    content = f'''
    <div class="card">
        <div class="card-header">🔔 Notifications</div>
        {rows}
    </div>
    '''
    return render_user_template(base_template, title="Notifications", active_page="notifications", content=content)

@app.route('/offer-skill')
def offer_skill():
    if 'user_id' not in session:
        return redirect('/login')
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM providers WHERE user_id=?", (user_id,))
    provider = c.fetchone()
    conn.close()
    if provider:
        return redirect('/edit-profile')
    else:
        return redirect('/create-profile')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        name = request.form['name'].strip()
        password = request.form['password']
        if not phone or not name or not password:
            return "All fields required. <a href='/signup'>Back</a>"
        hashed = generate_password_hash(password)
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO users (phone, name, password_hash) VALUES (?, ?, ?)", (phone, name, hashed))
            user_id = c.lastrowid
            conn.commit()
            # ---- PROCESS REFERRAL ----
            process_referral(user_id, phone)
            conn.close()
            add_notification(user_id, 'email', f'Welcome {name}! Your RockabyConnect account is ready.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return "Phone number already registered. <a href='/login'>Login</a>"
    return render_user_template(signup_page, title="Sign Up", active_page="signup")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        password = request.form['password']
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, name, password_hash FROM users WHERE phone=?", (phone,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['user_name'] = user[1]
            session['user_phone'] = phone
            return redirect(url_for('dashboard'))
        else:
            return "Invalid credentials. <a href='/login'>Try again</a>"
    return render_user_template(login_page, title="Login", active_page="login")

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/edit-name')
@login_required
def edit_name():
    content = edit_name_page.replace("{current_name}", session['user_name'])
    return render_user_template(content, title="Edit Name", active_page="")

@app.route('/update-name', methods=['POST'])
@login_required
def update_name():
    new_name = request.form['name'].strip()
    if not new_name:
        return "Name cannot be empty. <a href='/edit-name'>Back</a>"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET name=? WHERE id=?", (new_name, session['user_id']))
    conn.commit()
    conn.close()
    session['user_name'] = new_name
    return redirect('/dashboard')

@app.route('/dashboard')
@login_required
def dashboard():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()

    c.execute("SELECT * FROM providers WHERE user_id=?", (user_id,))
    provider = c.fetchone()

    c.execute("SELECT * FROM vendors WHERE user_id=?", (user_id,))
    vendor = c.fetchone()

    c.execute("SELECT id, title, status FROM jobs WHERE employer_id=? ORDER BY id DESC", (user_id,))
    jobs = c.fetchall()
    conn.close()

    # ---- Freelancer Profile Section ----
    profile_section = ""
    if provider:
        pid, _, skills, district, village, bio, pic, video, status, featured, featured_expiry = provider
        status_class = status.lower().replace(' ', '-')
        location = f"{district}{', ' + village if village else ''}"
        profile_section = f"""
            <div class="card">
                <div class="card-header">My Freelancer Profile</div>
                <p><strong>Skills:</strong> {skills}</p>
                <p><strong>Location:</strong> {location}</p>
                <p><strong>Status:</strong> <span class="badge badge-{status_class}">{status}</span></p>
                <div style="display:flex; gap:10px; margin-top:15px; flex-wrap:wrap;">
                    <a href="/edit-profile" class="btn btn-small">Edit Profile</a>
                    <a href="/boost" class="btn btn-small" style="background:var(--primary-dark);">Boost Profile</a>
                    <form method="POST" action="/delete-profile" style="display:inline;" onsubmit="return confirm('Are you sure you want to delete your freelancer profile? This cannot be undone.');">
                        <button type="submit" class="btn btn-small btn-danger">Delete Profile</button>
                    </form>
                </div>
            </div>
        """
    else:
        profile_section = """
            <div class="card">
                <p>You haven't created a freelancer profile yet.</p>
                <a href="/create-profile" class="btn">Create Profile</a>
            </div>
        """

    # ---- Vendor Profile Section ----
    vendor_section = ""
    if vendor:
        vid, _, bname, district, village, landmark, bio, vimg, vimg2, vimg3, vvideo, vstatus, vfeatured, vexpiry = vendor
        vstatus_class = vstatus.lower()
        location = f"{district}{', ' + village if village else ''}{', ' + landmark if landmark else ''}"
        vendor_section = f"""
            <div class="card">
                <div class="card-header">My Vendor Profile</div>
                <p><strong>Business:</strong> {bname}</p>
                <p><strong>Location:</strong> {location}</p>
                <p><strong>Status:</strong> <span class="badge badge-{vstatus_class}">{vstatus}</span></p>
                <div style="display:flex; gap:10px; margin-top:15px; flex-wrap:wrap;">
                    <a href="/edit-vendor-profile" class="btn btn-small">Edit Vendor Profile</a>
                    <a href="/boost-vendor" class="btn btn-small" style="background:var(--primary-dark);">Boost Vendor</a>
                    <form method="POST" action="/delete-vendor-profile" style="display:inline;" onsubmit="return confirm('Are you sure you want to delete your vendor profile? This cannot be undone.');">
                        <button type="submit" class="btn btn-small btn-danger">Delete Vendor</button>
                    </form>
                </div>
            </div>
        """
    else:
        vendor_section = """
            <div class="card">
                <p>You haven't created a vendor profile yet.</p>
                <a href="/create-vendor-profile" class="btn">Create Vendor Profile</a>
            </div>
        """

    # ---- Jobs Section ----
    jobs_html = ""
    if jobs:
        for job in jobs:
            jid, title, status = job
            badge_class = 'open' if status == 'Open' else ('taken' if status == 'Taken' else 'closed')
            jobs_html += f"""
                <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid var(--border);">
                    <span>{title} <span class="badge badge-{badge_class}">{status}</span></span>
                    <div style="display:flex; gap:5px; flex-wrap:wrap;">
                        <a href="/edit-job/{jid}" class="btn btn-small btn-outline">Edit</a>
                        <a href="/boost-job/{jid}" class="btn btn-small" style="background:var(--primary-dark);">Boost</a>
                        <form method="POST" action="/delete-job/{jid}" style="display:inline;" onsubmit="return confirm('Are you sure you want to delete this job? This cannot be undone.');">
                            <button type="submit" class="btn btn-small btn-danger">Delete</button>
                        </form>
                    </div>
                </div>
            """
    else:
        jobs_html = "<p>No jobs posted yet.</p>"

    # ---- Return with placeholders ----
    return render_user_template(
        dashboard_template,
        title="Dashboard",
        active_page="dashboard",
        profile_section=profile_section,
        vendor_section=vendor_section,
        jobs_html=jobs_html
    )

# ---------- Freelancer Profile (create/edit) ----------
@app.route('/create-profile', methods=['GET', 'POST'])
@login_required
def create_profile():
    user_id = session['user_id']
    
    # First, check if profile exists (read-only)
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM providers WHERE user_id=?", (user_id,))
        if c.fetchone():
            return redirect('/edit-profile')

    if request.method == 'POST':
        skills = request.form['skills'].strip()
        district = request.form['district'].strip()
        village = request.form.get('village', '').strip()
        bio = request.form.get('bio', '').strip()
        status = request.form.get('status', 'Available')
        file = request.files.get('profile_pic')
        video_file = request.files.get('video')

        filename = None
        video_filename = None
        if file and allowed_file(file.filename):
            filename = save_resized_image(file, max_width=800, max_height=600)
        if video_file and allowed_video(video_file.filename):
            video_filename = secure_filename(video_file.filename)
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
            video_file.save(video_path)

        # Write operation
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO providers (user_id, skills, district, village, bio, profile_pic, video, status)
                VALUES (?,?,?,?,?,?,?,?)
            """, (user_id, skills, district, village, bio, filename, video_filename, status))
            conn.commit()
        
        return redirect('/dashboard')

    # GET request – show form
    form_html = profile_form_template.replace("{form_title}", "Create Your Freelancer Profile")
    form_html = form_html.replace("{skills}", "")
    form_html = form_html.replace("{skill_suggestions}", ', '.join(SKILL_SUGGESTIONS[:10]) + ', ...')
    form_html = form_html.replace("{district}", "").replace("{village}", "").replace("{bio}", "")
    status_options = ''.join([f'<option value="{s}">{s}</option>' for s in FREELANCER_STATUSES])
    form_html = form_html.replace("{status_options}", status_options)
    return render_user_template(form_html, title="Create Profile", active_page="dashboard")

    except sqlite3.OperationalError as e:
        if conn:
            conn.close()
        return f"Database error: {str(e)}. Please try again.", 500
    finally:
        if conn:
            conn.close()
        return redirect('/dashboard')

    form_html = profile_form_template.replace("{form_title}", "Create Your Freelancer Profile")
    form_html = form_html.replace("{skills}", "")
    form_html = form_html.replace("{skill_suggestions}", ', '.join(SKILL_SUGGESTIONS[:10]) + ', ...')
    form_html = form_html.replace("{district}", "").replace("{village}", "").replace("{bio}", "")
    status_options = ''.join([f'<option value="{s}">{s}</option>' for s in FREELANCER_STATUSES])
    form_html = form_html.replace("{status_options}", status_options)
    return render_user_template(form_html, title="Create Profile", active_page="dashboard")

@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    c.execute("SELECT skills, district, village, bio, profile_pic, video, status FROM providers WHERE user_id=?", (user_id,))
    provider = c.fetchone()
    if not provider:
        conn.close()
        return redirect('/create-profile')

    if request.method == 'POST':
        skills = request.form['skills'].strip()
        district = request.form['district'].strip()
        village = request.form.get('village', '').strip()
        bio = request.form.get('bio', '').strip()
        status = request.form.get('status', 'Available')
        file = request.files.get('profile_pic')
        video_file = request.files.get('video')

        if file and allowed_file(file.filename):
            filename = save_resized_image(file, max_width=800, max_height=600)
        else:
            filename = provider[4]  # current profile_pic

        if video_file and allowed_video(video_file.filename):
            video_filename = secure_filename(video_file.filename)
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
            video_file.save(video_path)
        else:
            video_filename = provider[5]  # current video

        c.execute("""
            UPDATE providers SET skills=?, district=?, village=?, bio=?, profile_pic=?, video=?, status=?
            WHERE user_id=?
        """, (skills, district, village, bio, filename, video_filename, status, user_id))
        conn.commit()
        conn.close()
        return redirect('/dashboard')

    skills, district, village, bio, pic, video, status = provider
    form_html = profile_form_template.replace("{form_title}", "Edit Your Freelancer Profile")
    form_html = form_html.replace("{skills}", skills or '')
    form_html = form_html.replace("{skill_suggestions}", ', '.join(SKILL_SUGGESTIONS[:10]) + ', ...')
    form_html = form_html.replace("{district}", district or '')
    form_html = form_html.replace("{village}", village or '')
    form_html = form_html.replace("{bio}", bio or '')
    status_options = ''.join([f'<option value="{s}" {"selected" if s==status else ""}>{s}</option>' for s in FREELANCER_STATUSES])
    form_html = form_html.replace("{status_options}", status_options)
    conn.close()
    return render_user_template(form_html, title="Edit Profile", active_page="dashboard")

# ---------- Vendor Profile (create/edit) ----------
@app.route('/create-vendor-profile', methods=['GET', 'POST'])
@login_required
def create_vendor_profile():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    c.execute("SELECT id FROM vendors WHERE user_id=?", (user_id,))
    if c.fetchone():
        conn.close()
        return redirect('/edit-vendor-profile')
    conn.close()

    if request.method == 'POST':
        business_name = request.form['business_name'].strip()
        district = request.form['district'].strip()
        village = request.form.get('village', '').strip()
        landmark = request.form.get('landmark', '').strip()
        bio = request.form.get('bio', '').strip()
        status = request.form.get('status', 'Open')

        filenames = [None, None, None]
        for idx, field in enumerate(['vendor_image', 'vendor_image2', 'vendor_image3']):
            file = request.files.get(field)
            if file and allowed_file(file.filename):
                filenames[idx] = save_resized_image(file, max_width=800, max_height=600)

        video_file = request.files.get('video')
        video_filename = None
        if video_file and allowed_video(video_file.filename):
            video_filename = secure_filename(video_file.filename)
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
            video_file.save(video_path)

        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA busy_timeout = 30000;")
        c = conn.cursor()
        c.execute("""
            INSERT INTO vendors (user_id, business_name, district, village, landmark, bio, 
                                 vendor_image, vendor_image2, vendor_image3, video, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (user_id, business_name, district, village, landmark, bio, 
              filenames[0], filenames[1], filenames[2], video_filename, status))
        conn.commit()
        conn.close()
        return redirect('/dashboard')

    form = vendor_form_template.replace("{form_title}", "Create Your Vendor Profile")
    form = form.replace("{business_name}", "").replace("{district}", "").replace("{village}", "")
    form = form.replace("{landmark}", "").replace("{bio}", "")
    status_options = ''.join([f'<option value="{s}">{s}</option>' for s in VENDOR_STATUSES])
    form = form.replace("{status_options}", status_options)
    return render_user_template(form, title="Create Vendor Profile", active_page="dashboard")

@app.route('/edit-vendor-profile', methods=['GET', 'POST'])
@login_required
def edit_vendor_profile():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    c.execute("""
        SELECT business_name, district, village, landmark, bio, 
               vendor_image, vendor_image2, vendor_image3, video, status 
        FROM vendors WHERE user_id=?
    """, (user_id,))
    vendor = c.fetchone()
    if not vendor:
        conn.close()
        return redirect('/create-vendor-profile')

    if request.method == 'POST':
        business_name = request.form['business_name'].strip()
        district = request.form['district'].strip()
        village = request.form.get('village', '').strip()
        landmark = request.form.get('landmark', '').strip()
        bio = request.form.get('bio', '').strip()
        status = request.form.get('status', 'Open')

        current_images = [vendor[5], vendor[6], vendor[7]]
        for idx, field in enumerate(['vendor_image', 'vendor_image2', 'vendor_image3']):
            file = request.files.get(field)
            if file and allowed_file(file.filename):
                current_images[idx] = save_resized_image(file, max_width=800, max_height=600)

        video_file = request.files.get('video')
        video_filename = vendor[8]
        if video_file and allowed_video(video_file.filename):
            video_filename = secure_filename(video_file.filename)
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
            video_file.save(video_path)

        c.execute("""
            UPDATE vendors SET 
                business_name=?, district=?, village=?, landmark=?, bio=?, 
                vendor_image=?, vendor_image2=?, vendor_image3=?, video=?, status=?
            WHERE user_id=?
        """, (business_name, district, village, landmark, bio, 
              current_images[0], current_images[1], current_images[2], video_filename, status, user_id))
        conn.commit()
        conn.close()
        return redirect('/dashboard')

    bname, district, village, landmark, bio, img, img2, img3, video, status = vendor
    form = vendor_form_template.replace("{form_title}", "Edit Your Vendor Profile")
    form = form.replace("{business_name}", bname or '')
    form = form.replace("{district}", district or '')
    form = form.replace("{village}", village or '')
    form = form.replace("{landmark}", landmark or '')
    form = form.replace("{bio}", bio or '')
    status_options = ''.join([f'<option value="{s}" {"selected" if s==status else ""}>{s}</option>' for s in VENDOR_STATUSES])
    form = form.replace("{status_options}", status_options)
    conn.close()
    return render_user_template(form, title="Edit Vendor Profile", active_page="dashboard")

# ---------- Boost Vendor ----------
@app.route('/boost-vendor')
@login_required
def boost_vendor():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM vendors WHERE user_id=?", (user_id,))
    vendor = c.fetchone()
    conn.close()
    if not vendor:
        return redirect('/create-vendor-profile')
    content = """
        <div class="card">
            <div class="card-header">Boost Your Vendor Profile</div>
            <p>Get your shop at the top of the vendor list!</p>
            <p><strong>Pricing:</strong></p>
            <ul><li>7 days: <strong>UGX 5,000</strong></li><li>30 days: <strong>UGX 15,000</strong></li></ul>
            <hr>
            <p><strong>How to pay:</strong></p>
            <ol>
                <li>Send the amount to:<br>
                    <strong>MTN Mobile Money: 0785686404</strong><br>
                    <strong>Airtel: 0751318876</strong><br>
                    <strong>Name: Rocky Peter Abayo</strong>
                </li>
                <li>Enter the Transaction ID from your Mobile Money confirmation.</li>
            </ol>
            <form method="POST" action="/boost-vendor-submit">
                <label>Select Plan</label>
                <select name="plan" required>
                    <option value="7">7 Days - UGX 5,000</option>
                    <option value="30">30 Days - UGX 15,000</option>
                </select>
                <label>Mobile Money Transaction ID *</label>
                <input type="text" name="trans_id" required>
                <button type="submit" class="btn" style="margin-top:20px;">Submit for Verification</button>
            </form>
        </div>
    """
    return render_user_template(base_template, title="Boost Vendor", active_page="dashboard", content=content)

@app.route('/boost-vendor-submit', methods=['POST'])
@login_required
def boost_vendor_submit():
    trans_id = request.form['trans_id']
    plan = request.form['plan']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO boost_requests (user_id, transaction_id, plan, status, boost_type, item_id) VALUES (?,?,?,'pending','vendor',0)",
              (session['user_id'], trans_id, plan))
    conn.commit()
    conn.close()
    content = """
        <div class="card"><h2>Vendor Boost Submitted</h2><p>We'll verify and activate soon.</p><a href="/dashboard" class="btn">Back</a></div>
    """
    return render_user_template(base_template, title="Boost Submitted", active_page="dashboard", content=content)

# ---------- Boost Profile ----------
@app.route('/boost')
@login_required
def boost_profile():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM providers WHERE user_id=?", (user_id,))
    provider = c.fetchone()
    conn.close()
    if not provider:
        return redirect('/create-profile')
    content = """
        <div class="card">
            <div class="card-header">Boost Your Profile</div>
            <p>Get featured at the top of the search results and attract more customers!</p>
            <p><strong>Pricing:</strong></p>
            <ul><li>7 days: <strong>UGX 5,000</strong></li><li>30 days: <strong>UGX 15,000</strong></li></ul>
            <hr>
            <p><strong>How to pay:</strong></p>
            <ol>
                <li>Send the amount to:<br>
                    <strong>MTN Mobile Money: 0785686404</strong><br>
                    <strong>Airtel: 0751318876</strong><br>
                    <strong>Name: Rocky Peter Abayo</strong>
                </li>
                <li>Enter the Transaction ID from your Mobile Money confirmation.</li>
            </ol>
            <form method="POST" action="/boost-submit">
                <label>Select Plan</label>
                <select name="plan" required>
                    <option value="7">7 Days - UGX 5,000</option>
                    <option value="30">30 Days - UGX 15,000</option>
                </select>
                <label>Mobile Money Transaction ID *</label>
                <input type="text" name="trans_id" required>
                <button type="submit" class="btn" style="margin-top:20px;">Submit for Verification</button>
            </form>
        </div>
    """
    return render_user_template(base_template, title="Boost Profile", active_page="dashboard", content=content)

@app.route('/boost-submit', methods=['POST'])
@login_required
def boost_submit():
    trans_id = request.form['trans_id']
    plan = request.form['plan']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO boost_requests (user_id, transaction_id, plan, status, boost_type) VALUES (?,?,?,'pending','profile')",
              (session['user_id'], trans_id, plan))
    conn.commit()
    conn.close()
    add_notification(session['user_id'], 'sms', f'Boost request received (ID {trans_id}). We will verify shortly.')
    content = """
        <div class="card"><h2>Boost Request Submitted</h2><p>We'll verify and activate soon.</p><a href="/dashboard" class="btn">Back</a></div>
    """
    return render_user_template(base_template, title="Boost Submitted", active_page="dashboard", content=content)

# ---------- Boost Job ----------
@app.route('/boost-job/<int:job_id>')
@login_required
def boost_job(job_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, employer_id, title FROM jobs WHERE id=?", (job_id,))
    job = c.fetchone()
    conn.close()
    if not job or job[1] != session['user_id']:
        return "Job not found or unauthorized.", 404
    content = f"""
        <div class="card">
            <div class="card-header">Boost Job: {job[2]}</div>
            <p>Make your job listing stand out!</p>
            <p><strong>Pricing:</strong> UGX 5,000 (7 days), UGX 15,000 (30 days).</p>
            <hr>
            <p><strong>How to pay:</strong></p>
            <ol>
                <li>Send the amount to:<br>
                    <strong>MTN Mobile Money: 0785686404</strong><br>
                    <strong>Airtel: 0751318876</strong><br>
                    <strong>Name: Rocky Peter Abayo</strong>
                </li>
                <li>Enter the Transaction ID from your Mobile Money confirmation.</li>
            </ol>
            <form method="POST" action="/boost-job-submit/{job_id}">
                <label>Select Plan</label>
                <select name="plan" required>
                    <option value="7">7 Days - UGX 5,000</option>
                    <option value="30">30 Days - UGX 15,000</option>
                </select>
                <label>Mobile Money Transaction ID *</label>
                <input type="text" name="trans_id" required>
                <button type="submit" class="btn" style="margin-top:20px;">Submit</button>
            </form>
        </div>
    """
    return render_user_template(base_template, title="Boost Job", active_page="dashboard", content=content)

@app.route('/boost-job-submit/<int:job_id>', methods=['POST'])
@login_required
def boost_job_submit(job_id):
    trans_id = request.form['trans_id']
    plan = request.form['plan']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO boost_requests (user_id, transaction_id, plan, status, boost_type, item_id) VALUES (?,?,?,'pending','job',?)",
              (session['user_id'], trans_id, plan, job_id))
    conn.commit()
    conn.close()
    content = """
        <div class="card"><h2>Job Boost Submitted</h2><p>We'll verify and activate soon.</p><a href="/dashboard" class="btn">Back</a></div>
    """
    return render_user_template(base_template, title="Boost Submitted", active_page="dashboard", content=content)

# ---------- Job posting, editing ----------
@app.route('/post-job', methods=['GET', 'POST'])
@login_required
def post_job():
    if request.method == 'POST':
        title = request.form['title']
        company = request.form.get('company', '')
        description = request.form['description']
        location = request.form['location']
        village = request.form.get('village', '')
        contact = request.form.get('contact', '')
        file = request.files.get('job_image')
        video_file = request.files.get('video')

        filename = None
        video_filename = None
        if file and allowed_file(file.filename):
            filename = save_resized_image(file, max_width=800, max_height=600)
        if video_file and allowed_video(video_file.filename):
            video_filename = secure_filename(video_file.filename)
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
            video_file.save(video_path)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO jobs (employer_id, title, company, description, location, village, contact, status, job_image, video)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (session['user_id'], title, company, description, location, village, contact, 'Open', filename, video_filename))
        conn.commit()
        conn.close()
        return redirect('/dashboard')

    form = job_form_template.replace("{job_form_title}", "Post a Job").replace("{form_header}", "Post a New Job")
    form = form.replace("{title_val}", "").replace("{company_val}", "").replace("{description_val}", "")
    form = form.replace("{location_val}", "").replace("{village_val}", "").replace("{contact_val}", "")
    form = form.replace("{submit_button}", "Post Job")
    return render_user_template(form, title="Post a Job", active_page="jobs")

@app.route('/edit-job/<int:job_id>', methods=['GET', 'POST'])
@login_required
def edit_job(job_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT title, company, description, location, village, contact, status, employer_id, job_image, video FROM jobs WHERE id=?", (job_id,))
    job = c.fetchone()
    if not job or job[7] != session['user_id']:
        conn.close()
        return "Job not found or unauthorized.", 404

    if request.method == 'POST':
        title = request.form['title']
        company = request.form.get('company', '')
        description = request.form['description']
        location = request.form['location']
        village = request.form.get('village', '')
        contact = request.form.get('contact', '')
        status = request.form.get('status', 'Open')
        file = request.files.get('job_image')
        video_file = request.files.get('video')

        filename = job[8]
        video_filename = job[9]
        if file and allowed_file(file.filename):
            filename = save_resized_image(file, max_width=800, max_height=600)
        if video_file and allowed_video(video_file.filename):
            video_filename = secure_filename(video_file.filename)
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
            video_file.save(video_path)

        c.execute("""
            UPDATE jobs SET title=?, company=?, description=?, location=?, village=?, contact=?, status=?, job_image=?, video=?
            WHERE id=?
        """, (title, company, description, location, village, contact, status, filename, video_filename, job_id))
        conn.commit()
        conn.close()
        return redirect('/dashboard')

    form = job_form_template.replace("{job_form_title}", "Edit Job").replace("{form_header}", "Edit Job Posting")
    form = form.replace("{title_val}", job[0]).replace("{company_val}", job[1] or '').replace("{description_val}", job[2] or '')
    form = form.replace("{location_val}", job[3] or '').replace("{village_val}", job[4] or '').replace("{contact_val}", job[5] or '')
    form = form.replace("{submit_button}", "Update Job")
    status_dropdown = f"""
        <label>Status</label>
        <select name="status">
            <option value="Open" {"selected" if job[6]=='Open' else ''}>Open</option>
            <option value="Taken" {"selected" if job[6]=='Taken' else ''}>Taken</option>
            <option value="Closed" {"selected" if job[6]=='Closed' else ''}>Closed</option>
        </select>
    """
    form = form.replace('</form>', f'{status_dropdown}\n</form>')
    conn.close()
    return render_user_template(form, title="Edit Job", active_page="jobs")

# ---------- Public Listing ----------
@app.route('/list')
def list_providers():
    logged_in = 'user_id' in session
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute("UPDATE providers SET featured=0 WHERE featured=1 AND featured_expiry IS NOT NULL AND featured_expiry < ?", (today,))
    conn.commit()
    c.execute("""
        SELECT p.id, u.name, p.skills, u.phone, p.district, p.village, p.bio, p.profile_pic, p.status, p.featured, p.featured_expiry
        FROM providers p JOIN users u ON p.user_id = u.id
        ORDER BY CASE WHEN p.featured = 1 AND (p.featured_expiry IS NULL OR p.featured_expiry >= date('now')) THEN 0 ELSE 1 END, p.id DESC
    """)
    providers = c.fetchall()
    conn.close()

    cards_html = ""
    for p in providers:
        pid, name, skills, phone, district, village, bio, pic, status, featured, expiry = p
        status_class = status.lower().replace(' ', '-')
        img_tag = f'<img src="/static/uploads/{pic}" class="profile-pic" alt="{name}">' if pic else '<div class="profile-pic" style="background:#ddd; display:flex; align-items:center; justify-content:center; font-size:2rem;">👤</div>'
        active_featured = is_featured_now(featured, expiry)
        feat = '<span class="badge badge-available" style="background:var(--primary);">FEATURED</span>' if active_featured else ''
        location_display = f"{district}{', ' + village if village else ''}"
        if logged_in:
            phone_display = f'<p style="margin-top:5px;">📞 {phone}</p>'
            wa_button = f'<a href="{whatsapp_link(phone)}" target="_blank" class="btn btn-whatsapp btn-small">Chat on WhatsApp</a>' if phone else ''
        else:
            phone_display = '<p style="margin-top:5px; color:var(--text-secondary);">📞 <a href="/login">Sign in to view contact</a></p>'
            wa_button = ''
        cards_html += f"""
        <div class="provider-card">
            {img_tag}
            <div class="provider-info">
                <h3><a href="/provider/{pid}" style="color:inherit; text-decoration:none;">{name}</a> <span class="badge badge-{status_class}">{status}</span> {feat}</h3>
                <p class="meta"><strong>{skills}</strong> · {location_display}</p>
                <p>{bio or ''}</p>
                {phone_display}
                {wa_button}
            </div>
        </div>"""
    if not cards_html:
        cards_html = "<p>No providers yet.</p>"
    return render_user_template(list_page, title="Find Skills", active_page="list", cards=cards_html)

@app.route('/jobs')
def list_jobs():
    logged_in = 'user_id' in session
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute("UPDATE jobs SET featured=0 WHERE featured=1 AND featured_expiry IS NOT NULL AND featured_expiry < ?", (today,))
    conn.commit()
    c.execute("""
        SELECT j.id, j.title, j.company, j.description, j.location, j.village, j.contact, j.status, j.posted_date, j.job_image, j.featured, j.featured_expiry, j.employer_id
        FROM jobs j
        ORDER BY CASE WHEN j.featured = 1 AND (j.featured_expiry IS NULL OR j.featured_expiry >= date('now')) THEN 0 ELSE 1 END, j.id DESC
    """)
    jobs = c.fetchall()
    conn.close()

    jobs_html = ""
    for j in jobs:
        job_id, title, company, desc, loc, village, contact, status, posted_date, image, featured, expiry, employer_id = j
        badge_class = 'open' if status == 'Open' else ('taken' if status == 'Taken' else 'closed')
        if logged_in:
            contact_display = f'<p>Contact: {contact}'
            if is_phone_number(contact):
                contact_display += f' <a href="{whatsapp_link(contact)}" target="_blank" class="btn btn-whatsapp btn-small">Chat on WhatsApp</a>'
            contact_display += '</p>'
        else:
            contact_display = '<p style="color:var(--text-secondary);">Contact: <a href="/login">Sign in to view</a></p>'
        active_featured = is_featured_now(featured, expiry)
        feat_badge = '<span class="badge badge-available" style="background:var(--primary);">FEATURED</span>' if active_featured else ''
        location_display = f"{loc}{', ' + village if village else ''}"
        img_tag = f'<img src="/static/uploads/{image}" class="profile-pic" style="border-radius:8px;" alt="{title}">' if image else ''
        
        applicants_link = ""
        apply_link = ""
        if logged_in:
            if session.get('user_id') == employer_id:
                applicants_link = f'<a href="/job/{job_id}/applicants" class="btn btn-small" style="background:#17a2b8;">👥 View Applicants</a>'
            elif status == 'Open':
                apply_link = f'<a href="/apply/{job_id}" class="btn btn-small" style="background:#28a745;">📝 Apply</a>'

        # Build the job card – use a single f‑string with proper escaping
        jobs_html += f"""
        <div class="job-card">
            {img_tag}
            <div class="job-info">
                <h3><a href="/job/{job_id}" style="color:inherit; text-decoration:none;">{title}</a> <span class="badge badge-{badge_class}">{status}</span> {feat_badge}</h3>
                <p class="meta">{company or 'N/A'} · {location_display} · {posted_date[:10] if posted_date else ''}</p>
                <p>{desc}</p>
                {contact_display}
                <div style="margin-top:8px;">
                    {applicants_link}
                    {apply_link}
                    <a href="/job/{job_id}" class="btn btn-small btn-outline">View Details</a>
                </div>
            </div>
        </div>"""

    if not jobs_html:
        jobs_html = "<p>No jobs yet.</p>"
    return render_user_template(job_list_page, title="Jobs", active_page="jobs", jobs_html=jobs_html)

@app.route('/vendors')
def list_vendors():
    logged_in = 'user_id' in session
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute("UPDATE vendors SET featured=0 WHERE featured=1 AND featured_expiry IS NOT NULL AND featured_expiry < ?", (today,))
    conn.commit()
    c.execute("""
        SELECT v.id, v.business_name, v.district, v.village, v.landmark, v.bio, v.vendor_image, v.status, v.featured, v.featured_expiry, u.phone
        FROM vendors v JOIN users u ON v.user_id = u.id
        ORDER BY CASE WHEN v.featured = 1 AND (v.featured_expiry IS NULL OR v.featured_expiry >= date('now')) THEN 0 ELSE 1 END, v.id DESC
    """)
    vendors = c.fetchall()
    conn.close()

    cards = ""
    for v in vendors:
        vid, bname, district, village, landmark, bio, img, status, featured, expiry, phone = v
        status_class = status.lower()
        img_tag = f'<img src="/static/uploads/{img}" class="vendor-img" alt="{bname}">' if img else '<div class="vendor-img" style="background:#ddd; height:100px; display:flex; align-items:center; justify-content:center;">No Image</div>'
        active_feat = is_featured_now(featured, expiry)
        feat_badge = '<span class="badge badge-available" style="background:var(--primary);">FEATURED</span>' if active_feat else ''
        loc_display = f"{district}{', ' + village if village else ''}{', ' + landmark if landmark else ''}"
        if logged_in:
            contact = f'<p style="margin-top:5px;">📞 {phone} <a href="{whatsapp_link(phone)}" target="_blank" class="btn btn-whatsapp btn-small">WhatsApp</a></p>'
        else:
            contact = '<p style="margin-top:5px; color:var(--text-secondary);">📞 <a href="/login">Sign in to view contact</a></p>'
        cards += f"""
        <div class="vendor-card">
            {img_tag}
            <div class="vendor-info">
                <h3><a href="/vendor/{vid}" style="color:inherit; text-decoration:none;">{bname}</a> <span class="badge badge-{status_class}">{status}</span> {feat_badge}</h3>
                <p class="meta">{loc_display}</p>
                <p>{bio or ''}</p>
                {contact}
            </div>
        </div>"""
    if not cards:
        cards = "<p>No vendors yet.</p>"
    return render_user_template(vendor_list_page, title="Vendors", active_page="vendors", cards=cards)

# ---------- Detail Pages ----------
@app.route('/provider/<int:provider_id>')
def provider_detail(provider_id):
    logged_in = 'user_id' in session
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT p.id, u.name, p.skills, p.district, p.village, p.bio, 
               p.profile_pic, p.video, p.status, p.featured, p.featured_expiry, u.phone
        FROM providers p JOIN users u ON p.user_id = u.id WHERE p.id=?
    """, (provider_id,))
    provider = c.fetchone()
    if not provider:
        conn.close()
        return "Provider not found.", 404
    pid, name, skills, district, village, bio, pic, video, status, featured, expiry, phone = provider
    status_class = status.lower().replace(' ', '-')
    village_display = f", {village}" if village else ""
    img_url = f"/static/uploads/{pic}" if pic else "https://via.placeholder.com/120"
    active_featured = is_featured_now(featured, expiry)
    feat = '<span class="badge badge-available">FEATURED</span>' if active_featured else ''
    if logged_in:
        contact_display = f'<p><strong>Contact:</strong> {phone} <a href="{whatsapp_link(phone)}" target="_blank" class="btn btn-whatsapp btn-small">WhatsApp</a></p>'
    else:
        contact_display = '<p><strong>Contact:</strong> <a href="/login">Sign in to view</a></p>'

    # ---- Build video HTML ----
    video_display = ""
    if video:
        video_display = f'<video src="/static/uploads/{video}" controls style="width:100%; max-height:300px; border-radius:8px; margin-bottom:15px;"></video>'

    # ---- Reviews ----
    c.execute("""
        SELECT u.name, r.rating, r.comment, r.created_at FROM reviews r JOIN users u ON r.reviewer_id = u.id
        WHERE r.provider_id=? ORDER BY r.created_at DESC
    """, (provider_id,))
    reviews = c.fetchall()
    c.execute("SELECT AVG(rating), COUNT(*) FROM reviews WHERE provider_id=?", (provider_id,))
    avg_row = c.fetchone()
    avg_rating = round(avg_row[0], 1) if avg_row[0] else 0
    reviews_html = ""
    for rev in reviews:
        reviews_html += f"<div class='review-card'><strong>{rev[0]}</strong> - <span class='rating'>{'★'*rev[1]}{'☆'*(5-rev[1])}</span><br><small>{rev[3][:10]}</small><p>{rev[2]}</p></div>"
    if not reviews:
        reviews_html = "<p>No reviews yet.</p>"
    review_form = ""
    if logged_in:
        review_form = f"""
        <hr><h4>Leave a Review</h4>
        <form method="POST" action="/review/{provider_id}">
            <label>Rating</label>
            <select name="rating" required>
                <option value="">Select</option>
                <option value="5">★★★★★ (5)</option>
                <option value="4">★★★★☆ (4)</option>
                <option value="3">★★★☆☆ (3)</option>
                <option value="2">★★☆☆☆ (2)</option>
                <option value="1">★☆☆☆☆ (1)</option>
            </select>
            <label>Comment</label>
            <textarea name="comment" rows="2"></textarea>
            <button type="submit" class="btn" style="margin-top:10px;">Submit Review</button>
        </form>
        """
    else:
        review_form = "<p><a href='/login'>Login</a> to leave a review.</p>"

    detail_html = provider_detail_template
    detail_html = detail_html.replace("{provider_name}", name)
    detail_html = detail_html.replace("{img_url}", img_url)
    detail_html = detail_html.replace("{video_display}", video_display)
    detail_html = detail_html.replace("{skills}", skills)
    detail_html = detail_html.replace("{district}", district)
    detail_html = detail_html.replace("{village_display}", village_display)
    detail_html = detail_html.replace("{bio}", bio or 'No bio')
    detail_html = detail_html.replace("{status_class}", status_class)
    detail_html = detail_html.replace("{status}", status)
    detail_html = detail_html.replace("{feat}", feat)
    detail_html = detail_html.replace("{contact_display}", contact_display)
    detail_html = detail_html.replace("{avg_rating}", str(avg_rating))
    detail_html = detail_html.replace("{reviews_html}", reviews_html)
    detail_html = detail_html.replace("{review_form}", review_form)
    conn.close()
    return render_user_template(detail_html, title=f"Provider: {name}", active_page="list")

@app.route('/vendor/<int:vendor_id>')
def vendor_detail(vendor_id):
    logged_in = 'user_id' in session
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT v.business_name, v.district, v.village, v.landmark, v.bio, 
               v.vendor_image, v.vendor_image2, v.vendor_image3, v.video,
               v.status, v.featured, v.featured_expiry, u.phone
        FROM vendors v JOIN users u ON v.user_id = u.id WHERE v.id=?
    """, (vendor_id,))
    v = c.fetchone()
    if not v:
        conn.close()
        return "Vendor not found.", 404
    bname, district, village, landmark, bio, img, img2, img3, video, status, featured, expiry, phone = v
    status_class = status.lower()
    img_url = f"/static/uploads/{img}" if img else ""
    active_feat = is_featured_now(featured, expiry)
    feat = '<span class="badge badge-available">FEATURED</span>' if active_feat else ''
    village_display = f", {village}" if village else ""
    landmark_display = f", {landmark}" if landmark else ""
    if logged_in:
        contact_display = f'<p><strong>Contact:</strong> {phone} <a href="{whatsapp_link(phone)}" target="_blank" class="btn btn-whatsapp btn-small">WhatsApp</a></p>'
    else:
        contact_display = '<p><strong>Contact:</strong> <a href="/login">Sign in to view</a></p>'

    # ---- Build video HTML ----
    video_display = ""
    if video:
        video_display = f'<video src="/static/uploads/{video}" controls style="width:100%; max-height:300px; border-radius:8px; margin-bottom:15px;"></video>'

    # ---- Build extra images ----
    extra_images = ""
    if img2 or img3:
        extra_images = '<div class="vendor-img-gallery" style="display:flex; gap:10px; flex-wrap:wrap; margin-bottom:15px;">'
        if img2:
            extra_images += f'<img src="/static/uploads/{img2}" alt="Additional photo" style="width:100%; max-height:200px; object-fit:cover; border-radius:8px;">'
        if img3:
            extra_images += f'<img src="/static/uploads/{img3}" alt="Additional photo" style="width:100%; max-height:200px; object-fit:cover; border-radius:8px;">'
        extra_images += '</div>'

    detail_html = vendor_detail_template
    detail_html = detail_html.replace("{business_name}", bname)
    detail_html = detail_html.replace("{img_url}", img_url)
    detail_html = detail_html.replace("{extra_images}", extra_images)
    detail_html = detail_html.replace("{video_display}", video_display)
    detail_html = detail_html.replace("{district}", district)
    detail_html = detail_html.replace("{village_display}", village_display)
    detail_html = detail_html.replace("{landmark_display}", landmark_display)
    detail_html = detail_html.replace("{bio}", bio or 'No description')
    detail_html = detail_html.replace("{status_class}", status_class)
    detail_html = detail_html.replace("{status}", status)
    detail_html = detail_html.replace("{feat}", feat)
    detail_html = detail_html.replace("{contact_display}", contact_display)
    conn.close()
    return render_user_template(detail_html, title=f"Vendor: {bname}", active_page="vendors")

@app.route('/review/<int:provider_id>', methods=['POST'])
@login_required
def add_review(provider_id):
    rating = int(request.form['rating'])
    comment = request.form.get('comment', '')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO reviews (provider_id, reviewer_id, rating, comment) VALUES (?,?,?,?)",
              (provider_id, session['user_id'], rating, comment))
    conn.commit()
    conn.close()
    return redirect(f'/provider/{provider_id}')

# ---------- Referral ----------
@app.route('/refer')
@login_required
def refer():
    user_id = session['user_id']
    referral_code = get_referral_code(user_id)
    stats = get_referral_stats(user_id)
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    referrals = c.execute("""
        SELECT r.*, u.name as referred_name 
        FROM referrals r 
        LEFT JOIN users u ON r.referred_user_id = u.id 
        WHERE r.referrer_id = ? 
        ORDER BY r.created_at DESC LIMIT 20
    """, (user_id,)).fetchall()
    conn.close()
    
    referral_rows = ''
    if referrals:
        for r in referrals:
            status_badge = {
                'pending': '<span class="badge" style="background:#ffc107;color:#000;">Pending</span>',
                'completed': '<span class="badge" style="background:#17a2b8;color:#fff;">Completed</span>',
                'rewarded': '<span class="badge" style="background:#28a745;color:#fff;">Rewarded</span>'
            }.get(r[4], r[4])
            referred_display = r[9] if r[9] else (r[3] if r[3] else 'Unknown')
            referral_rows += f'''
            <tr>
                <td>{referred_display}</td>
                <td>{r[7][:16] if r[7] else '-'}</td>
                <td>{r[8][:16] if r[8] else '-'}</td>
                <td>{status_badge}</td>
                <td>UGX {r[5] or 0:,}</td>
            </tr>
            '''
    else:
        referral_rows = '<tr><td colspan="5" style="text-align:center;padding:20px;">No referrals yet. Share your link to get started!</td></tr>'
    
    base_url = request.base_url.replace('/refer', '')
    referral_link = f"{base_url}/?ref={referral_code}"
    
    content = f'''
    <div class="stat-grid" style="margin-bottom:20px;">
        <div class="stat-card">
            <h3>{stats['total']}</h3>
            <small>Total Referrals</small>
        </div>
        <div class="stat-card">
            <h3>{stats['pending']}</h3>
            <small>Pending</small>
        </div>
        <div class="stat-card">
            <h3>{stats['completed']}</h3>
            <small>Completed</small>
        </div>
        <div class="stat-card">
            <h3>UGX {stats['total_rewards']:,}</h3>
            <small>Total Rewards Earned</small>
        </div>
    </div>
    
    <div class="card">
        <div class="card-header"><i class="fas fa-share-alt"></i> Your Referral Link</div>
        <div style="display:flex; flex-wrap:wrap; gap:10px; align-items:center;">
            <input type="text" id="referralLink" value="{referral_link}" readonly 
                   style="flex:1; min-width:200px; padding:10px; border-radius:8px; border:1px solid var(--border); background:var(--card-bg); color:var(--text);">
            <button class="btn btn-success" onclick="copyReferralLink()">
                <i class="fas fa-copy"></i> Copy Link
            </button>
            <a href="https://wa.me/?text=Join%20RockabyConnect%20using%20my%20referral%20link%3A%20{referral_link}" 
               target="_blank" class="btn" style="background:#25D366; color:white;">
                <i class="fab fa-whatsapp"></i> Share
            </a>
            <a href="https://www.facebook.com/sharer/sharer.php?u={referral_link}" 
               target="_blank" class="btn" style="background:#1877f2; color:white;">
                <i class="fab fa-facebook"></i> Share
            </a>
        </div>
        <div style="margin-top:15px; padding:15px; background:var(--bg); border-radius:8px;">
            <p><strong>Referral Code:</strong> <code style="font-size:1.2rem; background:var(--card-bg); padding:4px 12px; border-radius:6px;">{referral_code}</code></p>
            <p style="color:var(--text-secondary); font-size:0.9rem;">
                <i class="fas fa-info-circle"></i> Share your referral link with friends. When they sign up, you earn rewards!
            </p>
        </div>
    </div>
    
    <div class="card">
        <div class="card-header"><i class="fas fa-history"></i> Referral History</div>
        <div class="table-responsive" style="overflow-x:auto;">
            <table>
                <thead>
                    <tr><th>Referred User</th><th>Date</th><th>Completed</th><th>Status</th><th>Reward</th></tr>
                </thead>
                <tbody>{referral_rows}</tbody>
            </table>
        </div>
    </div>
    
    <script>
        function copyReferralLink() {{
            var link = document.getElementById('referralLink');
            link.select();
            document.execCommand('copy');
            var btn = event.target.closest('button');
            var originalText = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
            setTimeout(function() {{
                btn.innerHTML = originalText;
            }}, 2000);
        }}
    </script>
    '''
    return render_user_template(base_template, title="Refer a Friend", active_page="", content=content)

# ---------- Settings ----------
@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    user_id = session['user_id']
    current_theme = get_user_theme(user_id)
    if 'user_theme' in session:
        current_theme = session['user_theme']
    
    if request.method == 'POST':
        theme = request.form.get('theme', 'default')
        if theme in ['default', 'neon']:
            set_user_theme(user_id, theme)
            session['user_theme'] = theme
            return redirect('/settings')
        else:
            return "Invalid theme", 400
    
    theme_options = f'''
    <select name="theme" style="width:auto; min-width:200px; padding:10px; border-radius:12px; border:1px solid var(--border); background:var(--card-bg); color:var(--text);">
        <option value="default" {"selected" if current_theme == 'default' else ""}>Default – Original Design</option>
        <option value="neon" {"selected" if current_theme == 'neon' else ""}>Neon – Vibrant & Glowing</option>
    </select>
    '''
    
    content = f'''
    <div class="card">
        <div class="card-header">⚙️ Settings</div>
        <form method="POST">
            <label>Theme Preference</label>
            {theme_options}
            <small style="display:block; color:var(--text-secondary); margin-top:5px;">Choose the look of your RockabyConnect experience.</small>
            <button type="submit" class="btn" style="margin-top:20px;">Save Settings</button>
        </form>
    </div>
    '''
    return render_user_template(base_template, title="Settings", active_page="settings", content=content)

# ============================================================
# ADMIN ROUTES (FULL SET)
# ============================================================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/admin/dashboard')
        else:
            content = """
            <div class="card" style="max-width: 500px; margin: 0 auto;">
                <div class="card-header">🔐 Admin Login</div>
                <div class="alert alert-error">Wrong password. Please try again.</div>
                <form method="POST">
                    <label>Password</label>
                    <input type="password" name="password" required>
                    <button type="submit" class="btn" style="width:100%; margin-top:20px;">Login</button>
                </form>
            </div>
            """
            return render_template_string(admin_base_template.replace("{title}", "Login").replace("{active_page}", "").replace("{content}", content))
    
    content = """
    <div class="card" style="max-width: 500px; margin: 0 auto;">
        <div class="card-header">🔐 Admin Login</div>
        <form method="POST">
            <label>Password</label>
            <input type="password" name="password" required>
            <button type="submit" class="btn" style="width:100%; margin-top:20px;">Login</button>
        </form>
    </div>
    """
    return render_template_string(admin_base_template.replace("{title}", "Login").replace("{active_page}", "").replace("{content}", content))

@app.route('/admin')
def admin_panel_redirect():
    if session.get('admin'):
        return redirect('/admin/dashboard')
    return redirect('/admin/login')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect('/admin/login')
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()

    # Stats
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM providers")
    total_providers = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM vendors")
    total_vendors = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = c.fetchone()[0]
    c.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
    job_stats = dict(c.fetchall())
    c.execute("SELECT COUNT(*) FROM boost_requests WHERE status='pending'")
    pending_boosts = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM boost_requests WHERE status='approved'")
    approved_boosts = c.fetchone()[0]
    c.execute("SELECT plan FROM boost_requests WHERE status='approved'")
    plans = c.fetchall()
    total_revenue = 0
    for (plan,) in plans:
        if plan == '7':
            total_revenue += 5000
        elif plan == '30':
            total_revenue += 15000
        elif plan == '90':
            total_revenue += 40000
        else:
            try:
                days = int(plan)
                if days == 7:
                    total_revenue += 5000
                elif days == 30:
                    total_revenue += 15000
                elif days == 90:
                    total_revenue += 40000
            except:
                pass
    conn.close()

    # Pending boost requests
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    c.execute("""
        SELECT br.id, u.phone, u.name, br.transaction_id, br.plan, br.boost_type, br.item_id, br.request_date
        FROM boost_requests br JOIN users u ON br.user_id = u.id
        WHERE br.status = 'pending' ORDER BY br.request_date DESC
    """)
    pending = c.fetchall()
    conn.close()

    rows = ""
    for req in pending:
        rid, phone, name, trans, plan, btype, item_id, rdate = req
        rows += f"""
        <tr>
            <td>{name}<br><small>{phone}</small></td>
            <td>{trans}</td>
            <td>{plan} days</td>
            <td><span class="badge" style="background:var(--primary); color:white; padding:2px 10px; border-radius:12px;">{btype}</span></td>
            <td><small>{rdate[:16] if rdate else ''}</small></td>
            <td>
                <a href="/admin/approve-boost/{rid}" class="btn btn-small" style="background:#28a745;">Approve</a>
                <a href="/admin/reject-boost/{rid}" class="btn btn-small btn-danger">Reject</a>
            </td>
        </tr>"""
    if not rows:
        rows = "<tr><td colspan='6' style='text-align:center;'>No pending boost requests.</td></tr>"

    content = f"""
    <div class="card">
        <div class="card-header">📊 Platform Statistics</div>
        <div class="stat-grid">
            <div class="stat-card"><h3>{total_users}</h3><small>Total Users</small></div>
            <div class="stat-card"><h3>{total_providers}</h3><small>Freelancers</small></div>
            <div class="stat-card"><h3>{total_vendors}</h3><small>Vendors</small></div>
            <div class="stat-card"><h3>{total_jobs}</h3><small>Total Jobs</small></div>
            <div class="stat-card"><h3>{job_stats.get('Open', 0)}</h3><small>Open Jobs</small></div>
            <div class="stat-card"><h3>{pending_boosts}</h3><small>Pending Boosts</small></div>
            <div class="stat-card"><h3>{approved_boosts}</h3><small>Approved Boosts</small></div>
            <div class="stat-card"><h3>UGX {total_revenue:,}</h3><small>Total Revenue</small></div>
        </div>
    </div>

    <div class="card">
        <div class="card-header">⏳ Pending Boost Requests</div>
        <table>
            <thead>
                <tr><th>User</th><th>Transaction</th><th>Plan</th><th>Type</th><th>Date</th><th>Action</th></tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        <div style="margin-top:20px;">
            <a href="/admin/stats" class="btn btn-outline">📊 Detailed Statistics</a>
            <a href="/admin/referral-settings" class="btn" style="background:#fd7e14; color:white;">🎁 Referral Settings</a>
        </div>
    </div>
    """
    return render_template_string(admin_base_template.replace("{title}", "Dashboard").replace("{active_page}", "dashboard").replace("{content}", content))

@app.route('/admin/stats')
def admin_stats():
    if not session.get('admin'):
        return redirect('/admin/login')
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM providers")
    total_providers = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM vendors")
    total_vendors = c.fetchone()[0]
    c.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
    job_counts = dict(c.fetchall())
    open_jobs = job_counts.get('Open', 0)
    taken_jobs = job_counts.get('Taken', 0)
    closed_jobs = job_counts.get('Closed', 0)
    c.execute("SELECT status, COUNT(*) FROM vendors GROUP BY status")
    vendor_counts = dict(c.fetchall())
    open_vendors = vendor_counts.get('Open', 0)
    closed_vendors = vendor_counts.get('Closed', 0)
    away_vendors = vendor_counts.get('Away', 0)
    c.execute("SELECT COUNT(*) FROM boost_requests WHERE status='pending'")
    pending_boosts = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM boost_requests WHERE status='approved'")
    approved_boosts = c.fetchone()[0]
    c.execute("SELECT plan, COUNT(*) FROM boost_requests WHERE status='approved' GROUP BY plan")
    plan_breakdown = c.fetchall()
    revenue_by_plan = []
    for plan, count in plan_breakdown:
        price = 5000 if plan == '7' else 15000 if plan == '30' else 40000 if plan == '90' else 0
        revenue_by_plan.append((plan, count, price, count * price))
    c.execute("SELECT skills FROM providers WHERE skills IS NOT NULL AND skills != ''")
    skill_rows = c.fetchall()
    skill_counter = defaultdict(int)
    for (skills_str,) in skill_rows:
        for skill in skills_str.split(','):
            skill = skill.strip().title()
            if skill:
                skill_counter[skill] += 1
    top_skills = sorted(skill_counter.items(), key=lambda x: x[1], reverse=True)[:5]
    top_skills_html = "".join(f"<tr><td>{skill}</td><td>{cnt}</td></tr>" for skill, cnt in top_skills) or "<tr><td colspan='2'>No skills yet.</td></tr>"
    conn.close()

    content = f"""
    <div class="card">
        <div class="card-header">📊 Detailed Statistics</div>
        <div class="stat-grid">
            <div class="stat-card"><h3>{total_users}</h3><small>Total Users</small></div>
            <div class="stat-card"><h3>{total_providers}</h3><small>Freelancers</small></div>
            <div class="stat-card"><h3>{total_vendors}</h3><small>Vendors</small></div>
            <div class="stat-card"><h3>{open_jobs}</h3><small>Open Jobs</small></div>
            <div class="stat-card"><h3>{taken_jobs}</h3><small>Taken Jobs</small></div>
            <div class="stat-card"><h3>{closed_jobs}</h3><small>Closed Jobs</small></div>
            <div class="stat-card"><h3>{open_vendors}</h3><small>Open Vendors</small></div>
            <div class="stat-card"><h3>{closed_vendors}</h3><small>Closed Vendors</small></div>
            <div class="stat-card"><h3>{away_vendors}</h3><small>Away Vendors</small></div>
            <div class="stat-card"><h3>{pending_boosts}</h3><small>Pending Boosts</small></div>
            <div class="stat-card"><h3>{approved_boosts}</h3><small>Approved Boosts</small></div>
        </div>
    </div>

    <div class="card">
        <div class="card-header">💪 Top 5 Skills</div>
        <table>
            <thead><tr><th>Skill</th><th>Freelancers</th></tr></thead>
            <tbody>{top_skills_html}</tbody>
        </table>
    </div>

    <div class="card">
        <div class="card-header">📈 Revenue by Plan</div>
        <ul>
    """
    if revenue_by_plan:
        for plan, count, price, total in revenue_by_plan:
            content += f"<li>{plan} days: {count} boosts = UGX {total:,}</li>"
    else:
        content += "<li>No approved boosts yet.</li>"
    content += """
        </ul>
        <div style="margin-top:20px;">
            <a href="/admin/dashboard" class="btn btn-outline">Back to Dashboard</a>
        </div>
    </div>
    """
    return render_template_string(admin_base_template.replace("{title}", "Statistics").replace("{active_page}", "stats").replace("{content}", content))

# --- Boost approval/rejection ---
@app.route('/admin/approve-boost/<int:req_id>')
def admin_approve_boost(req_id):
    if not session.get('admin'):
        return redirect('/admin/login')
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    
    c.execute("SELECT user_id, plan, boost_type, item_id FROM boost_requests WHERE id=?", (req_id,))
    req = c.fetchone()
    if req:
        user_id, plan, btype, item_id = req
        days = int(plan)
        expiry = date.today() + timedelta(days=days)
        if btype == 'profile':
            c.execute("UPDATE providers SET featured=1, featured_expiry=? WHERE user_id=?", (expiry, user_id))
        elif btype == 'job':
            c.execute("UPDATE jobs SET featured=1, featured_expiry=? WHERE id=?", (expiry, item_id))
        elif btype == 'vendor':
            c.execute("UPDATE vendors SET featured=1, featured_expiry=? WHERE user_id=?", (expiry, user_id))
        c.execute("UPDATE boost_requests SET status='approved' WHERE id=?", (req_id,))
        conn.commit()
        add_notification(user_id, 'sms', 'Your boost has been approved and is now live!')
    
    conn.close()
    return redirect('/admin/dashboard')

@app.route('/admin/reject-boost/<int:req_id>')
def admin_reject_boost(req_id):
    if not session.get('admin'):
        return redirect('/admin/login')
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 30000;")
    c = conn.cursor()
    c.execute("UPDATE boost_requests SET status='rejected' WHERE id=?", (req_id,))
    conn.commit()
    conn.close()
    return redirect('/admin/dashboard')

# --- Admin Backup and Restore ---
@app.route('/admin/backup')
def admin_backup():
    if not session.get('admin'):
        return redirect('/admin/login')
    
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"backup_{timestamp}.db"
        backup_path = os.path.join(BACKUP_DIR, backup_filename)
        shutil.copy2(DB_PATH, backup_path)
        
        content = f"""
        <div class="card" style="text-align:center;">
            <div class="card-header">✅ Backup Created</div>
            <p>File: <strong>{backup_filename}</strong></p>
            <a href="/admin/download-backup/{backup_filename}" class="btn">Download</a>
            <a href="/admin/backups" class="btn btn-outline">View All Backups</a>
        </div>
        """
        return render_template_string(admin_base_template.replace("{title}", "Backup Created").replace("{active_page}", "backups").replace("{content}", content))
    except Exception as e:
        return f"Backup failed: {e}", 500

@app.route('/admin/backups')
def admin_backups():
    if not session.get('admin'):
        return redirect('/admin/login')
    
    backups = []
    for f in os.listdir(BACKUP_DIR):
        if f.endswith('.db'):
            stat = os.stat(os.path.join(BACKUP_DIR, f))
            backups.append({
                'name': f,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })
    backups.sort(key=lambda x: x['modified'], reverse=True)
    
    rows = ""
    for b in backups:
        rows += f"""
        <tr>
            <td>{b['name']}</td>
            <td>{b['modified']}</td>
            <td>{b['size'] // 1024} KB</td>
            <td><a href="/admin/download-backup/{b['name']}" class="btn btn-small">Download</a></td>
        </tr>"""
    
    if not rows:
        rows = "<tr><td colspan='4'>No backups found.</td></tr>"
    
    content = f"""
    <div class="card">
        <div class="card-header">💾 Database Backups</div>
        <div style="display:flex; gap:10px; flex-wrap:wrap; margin-bottom:20px;">
            <a href="/admin/backup" class="btn">Create New Backup</a>
            <a href="/admin/download-current-db" class="btn btn-outline">Download Current DB</a>
            <a href="/admin/restore" class="btn" style="background: #28a745;">📤 Restore from Backup</a>
        </div>
        <table>
            <thead>
                <tr><th>Filename</th><th>Modified</th><th>Size</th><th>Action</th></tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        <div style="margin-top:20px;">
            <a href="/admin/dashboard" class="btn btn-outline">Back to Dashboard</a>
        </div>
    </div>
    """
    return render_template_string(admin_base_template.replace("{title}", "Backups").replace("{active_page}", "backups").replace("{content}", content))

@app.route('/admin/download-backup/<filename>')
def admin_download_backup(filename):
    if not session.get('admin'):
        return redirect('/admin/login')
    
    if '..' in filename or '/' in filename:
        return "Invalid filename", 400
    
    backup_path = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(backup_path):
        return "Backup not found", 404
    
    return send_file(backup_path, as_attachment=True, download_name=filename)

@app.route('/admin/download-current-db')
def admin_download_current_db():
    if not session.get('admin'):
        return redirect('/admin/login')
    
    if not os.path.exists(DB_PATH):
        return "Database not found", 404
    
    return send_file(DB_PATH, as_attachment=True, download_name='rockabyconnect_current.db')

@app.route('/admin/restore', methods=['GET', 'POST'])
def admin_restore():
    if not session.get('admin'):
        return redirect('/admin/login')
    
    if request.method == 'POST':
        if 'backup_file' not in request.files:
            return render_template_string(admin_base_template.replace("{title}", "Restore").replace("{active_page}", "").replace("{content}", """
            <div class="card"><div class="alert alert-error">No file uploaded.</div><a href="/admin/restore" class="btn">Try again</a></div>
            """))
        
        file = request.files['backup_file']
        if file.filename == '':
            return render_template_string(admin_base_template.replace("{title}", "Restore").replace("{active_page}", "").replace("{content}", """
            <div class="card"><div class="alert alert-error">No file selected.</div><a href="/admin/restore" class="btn">Try again</a></div>
            """))
        
        temp_path = '/tmp/restore_temp.db'
        file.save(temp_path)
        
        try:
            test_conn = sqlite3.connect(temp_path)
            test_conn.execute("SELECT 1")
            test_conn.close()
        except Exception as e:
            return render_template_string(admin_base_template.replace("{title}", "Restore").replace("{active_page}", "").replace("{content}", f"""
            <div class="card"><div class="alert alert-error">Invalid database file: {e}</div><a href="/admin/restore" class="btn">Try again</a></div>
            """))
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_before_restore = os.path.join(BACKUP_DIR, f"pre_restore_{timestamp}.db")
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, backup_before_restore)
        shutil.copy2(temp_path, DB_PATH)
        os.remove(temp_path)
        
        content = f"""
        <div class="card" style="text-align:center;">
            <div class="card-header">✅ Database Restored</div>
            <p>The database has been replaced with the uploaded backup.</p>
            <p>A backup of the previous database was saved as: <strong>pre_restore_{timestamp}.db</strong></p>
            <a href="/admin/backups" class="btn">View Backups</a>
            <a href="/admin/dashboard" class="btn btn-outline">Back to Dashboard</a>
        </div>
        """
        return render_template_string(admin_base_template.replace("{title}", "Restore Complete").replace("{active_page}", "backups").replace("{content}", content))
    
    content = """
    <div class="card">
        <div class="card-header">⬆️ Restore Database from Backup</div>
        <div class="alert alert-error" style="background:rgba(255,193,7,0.15); border-color:rgba(255,193,7,0.3); color:#856404;">
            <strong>⚠️ Warning:</strong> This will overwrite your current database. The current database will be backed up automatically before restoration.
        </div>
        <form method="POST" enctype="multipart/form-data">
            <label>Select a backup file (.db)</label>
            <input type="file" name="backup_file" accept=".db" required>
            <button type="submit" class="btn" style="margin-top:20px;">Restore Database</button>
        </form>
        <div style="margin-top:20px;">
            <a href="/admin/backups" class="btn btn-outline">Back to Backups</a>
        </div>
    </div>
    """
    return render_template_string(admin_base_template.replace("{title}", "Restore Database").replace("{active_page}", "backups").replace("{content}", content))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin/login')

# ============================================================
# FIX DATABASE / DEBUG ROUTES
# ============================================================
@app.route('/fix-video-column')
def fix_video_column():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for table in ['providers', 'vendors', 'jobs']:
        c.execute(f"PRAGMA table_info({table})")
        existing = [row[1] for row in c.fetchall()]
        if 'video' not in existing:
            c.execute(f"ALTER TABLE {table} ADD COLUMN video TEXT")
            print(f"Added video to {table}")
    conn.commit()
    conn.close()
    return "Video columns added."

@app.route('/fix-db')
def fix_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for table in ['providers', 'vendors', 'jobs']:
        c.execute(f"PRAGMA table_info({table})")
        existing = [row[1] for row in c.fetchall()]
        if 'video' not in existing:
            c.execute(f"ALTER TABLE {table} ADD COLUMN video TEXT")
            print(f"Added video column to {table}")
    conn.commit()
    conn.close()
    return "Database fixed. <a href='/debug'>Check debug</a>"

@app.route('/debug')
def debug_info():
    import traceback
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        result = ""
        for table in ['providers', 'vendors', 'jobs']:
            c.execute(f"PRAGMA table_info({table})")
            cols = [row[1] for row in c.fetchall()]
            result += f"<br><b>{table}:</b> {', '.join(cols)}"
        conn.close()
        return f"""
        <h2>Debug Info</h2>
        <p>Database tables and columns:</p>
        {result}
        <br><br>
        <p>Session: {dict(session) if session else 'No session'}</p>
        """
    except Exception as e:
        return f"<h2>Error</h2><pre>{traceback.format_exc()}</pre>"

@app.route('/debug-config')
def debug_config():
    max_size = app.config.get('MAX_CONTENT_LENGTH')
    return f"MAX_CONTENT_LENGTH = {max_size} bytes ({max_size // (1024*1024)} MB)"

@app.errorhandler(413)
def too_large(e):
    return "File too large. Maximum size is 1 GB.", 413

@app.route('/apply/<int:job_id>', methods=['GET', 'POST'])
@login_required
def apply_job(job_id):
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT title, employer_id FROM jobs WHERE id=? AND status='Open'", (job_id,))
    job = c.fetchone()
    if not job:
        conn.close()
        return "Job not available for applications.", 404
    if job[1] == user_id:
        conn.close()
        return "You cannot apply to your own job.", 400
    c.execute("SELECT id FROM job_applications WHERE job_id=? AND applicant_id=?", (job_id, user_id))
    if c.fetchone():
        conn.close()
        return "You have already applied to this job.", 400

    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        attachment = request.files.get('attachment')
        filename = None
        if attachment and allowed_file(attachment.filename):
            filename = secure_filename(attachment.filename)
            attachment.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        c.execute("""
            INSERT INTO job_applications (job_id, applicant_id, message, attachment)
            VALUES (?,?,?,?)
        """, (job_id, user_id, message, filename))
        conn.commit()
        # ---- NOTIFICATION ----
        add_notification(job[1], 'job_application', f'{session["user_name"]} applied for "{job[0]}"', link=f'/job/{job_id}/applicants')
        # ---------------------
        conn.close()
        return redirect(url_for('my_applications'))

    # GET – show form
    content = f'''
    <div class="card">
        <div class="card-header">Apply for: {job[0]}</div>
        <form method="POST" enctype="multipart/form-data">
            <label>Message (optional)</label>
            <textarea name="message" rows="4" placeholder="Why are you the right person for this job?"></textarea>
            <label>Attachment (optional – resume, portfolio)</label>
            <input type="file" name="attachment" accept=".pdf,.doc,.docx,.txt,.jpg,.png">
            <button type="submit" class="btn" style="margin-top:20px;">Submit Application</button>
        </form>
    </div>
    '''
    conn.close()
    return render_user_template(base_template, title="Apply to Job", active_page="jobs", content=content)


@app.route('/my-applications')
@login_required
def my_applications():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT a.id, j.title, a.status, a.created_at, a.updated_at, j.id as job_id
        FROM job_applications a
        JOIN jobs j ON a.job_id = j.id
        WHERE a.applicant_id = ?
        ORDER BY a.created_at DESC
    """, (user_id,))
    apps = c.fetchall()
    conn.close()

    rows = ""
    for app in apps:
        status_badge = get_application_status_badge(app[2])
        rows += f"""
        <tr>
            <td><a href="/job/{app[5]}">{app[1]}</a></td>
            <td>{status_badge}</td>
            <td>{app[3][:16] if app[3] else '-'}</td>
            <td>{app[4][:16] if app[4] else '-'}</td>
            <td><a href="/application/{app[0]}" class="btn btn-small">View</a></td>
        </tr>
        """
    if not rows:
        rows = '<tr><td colspan="5">You have not applied to any jobs yet.</td></tr>'

    content = f'''
    <div class="card">
        <div class="card-header">My Applications</div>
        <table>
            <thead><tr><th>Job</th><th>Status</th><th>Applied</th><th>Updated</th><th>Action</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    '''
    return render_user_template(base_template, title="My Applications", active_page="jobs", content=content)


@app.route('/application/<int:app_id>')
@login_required
def view_application(app_id):
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT a.id, a.job_id, a.applicant_id, a.message, a.attachment, a.status, a.created_at, a.updated_at,
               j.title, j.employer_id
        FROM job_applications a
        JOIN jobs j ON a.job_id = j.id
        WHERE a.id = ?
    """, (app_id,))
    app = c.fetchone()
    if not app:
        conn.close()
        return "Application not found.", 404
    # Check permission: either the applicant or the employer
    if app[2] != user_id and app[9] != user_id:
        conn.close()
        return "You do not have permission to view this application.", 403

    # Get applicant name and employer name
    applicant_name = get_user_name(app[2])
    employer_name = get_user_name(app[9])

    # Get applicant's provider profile (for profile link)
    c.execute("""
        SELECT p.id, u.name, u.phone, p.skills, p.district, p.village, p.profile_pic
        FROM providers p
        JOIN users u ON p.user_id = u.id
        WHERE p.user_id = ?
    """, (app[2],))
    applicant_provider = c.fetchone()

    # ---- Build applicant profile link and message button ----
    applicant_profile_link = ""
    message_button = ""
    if applicant_provider:
        provider_id = applicant_provider[0]
        applicant_profile_link = f'<a href="/provider/{provider_id}" class="btn btn-small" style="background:#17a2b8;">👤 View Profile</a>'
        message_button = f'<a href="/messages/{app[2]}" class="btn btn-small" style="background:#28a745;">💬 Message</a>'
    else:
        # If no provider profile, show user ID or phone
        applicant_profile_link = f'<p><strong>User ID:</strong> {app[2]}</p>'
        message_button = f'<a href="/messages/{app[2]}" class="btn btn-small" style="background:#28a745;">💬 Message</a>'

    # Get notes
    c.execute("""
        SELECT note, created_by, created_at
        FROM application_notes
        WHERE application_id = ?
        ORDER BY created_at DESC
    """, (app_id,))
    notes = c.fetchall()
    notes_html = ""
    for note in notes:
        by = get_user_name(note[1])
        notes_html += f"""
        <div class="review-card" style="border-left-color:var(--primary);">
            <p>{note[0]}</p>
            <small>— {by} at {note[2][:16]}</small>
        </div>
        """
    if not notes:
        notes_html = "<p>No notes yet.</p>"

    # ---- Build attachment download link ----
    attachment_link = ""
    if app[4]:  # attachment filename exists
        attachment_link = f'<a href="/download/{app[4]}" class="btn btn-small" style="background:#6c757d;" target="_blank">📄 Download Attachment</a>'

    # Status update form (only for employer)
    status_form = ""
    if app[9] == user_id:
        status_form = f"""
        <form method="POST" action="/application/{app_id}/status" style="display:inline;">
            <select name="status" class="btn-small">
                <option value="pending" {'selected' if app[5]=='pending' else ''}>Pending</option>
                <option value="reviewed" {'selected' if app[5]=='reviewed' else ''}>Reviewed</option>
                <option value="shortlisted" {'selected' if app[5]=='shortlisted' else ''}>Shortlisted</option>
                <option value="rejected" {'selected' if app[5]=='rejected' else ''}>Rejected</option>
                <option value="hired" {'selected' if app[5]=='hired' else ''}>Hired</option>
            </select>
            <button type="submit" class="btn btn-small">Update</button>
        </form>
        <form method="POST" action="/application/{app_id}/note" style="display:inline;">
            <input type="text" name="note" placeholder="Add a note..." style="width:200px;">
            <button type="submit" class="btn btn-small">Add Note</button>
        </form>
        """

    content = f'''
    <div class="card">
        <div class="card-header">Application #{app[0]} – {app[1]}</div>
        <p><strong>Job:</strong> {app[8]}</p>
        <p><strong>Applicant:</strong> {applicant_name}</p>
        <div style="display:flex; gap:10px; flex-wrap:wrap; margin:10px 0;">
            {applicant_profile_link}
            {message_button}
        </div>
        <p><strong>Message:</strong> {app[3] or 'No message'}</p>
        <p><strong>Attachment:</strong> {attachment_link or 'None'}</p>
        <p><strong>Status:</strong> {get_application_status_badge(app[5])}</p>
        <p><strong>Applied:</strong> {app[6][:16]} <strong>Updated:</strong> {app[7][:16]}</p>
        {status_form}
        <hr>
        <h4>Notes</h4>
        {notes_html}
        <p><a href="/my-applications" class="btn btn-outline">Back</a></p>
    </div>
    '''
    conn.close()
    return render_user_template(base_template, title="Application Details", active_page="jobs", content=content)


@app.route('/application/<int:app_id>/status', methods=['POST'])
@login_required
def update_application_status(app_id):
    new_status = request.form.get('status')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT a.job_id, a.applicant_id, j.title
        FROM job_applications a
        JOIN jobs j ON a.job_id = j.id
        WHERE a.id=?
    """, (app_id,))
    app = c.fetchone()
    if not app:
        conn.close()
        return "Application not found.", 404
    # Check employer
    c.execute("SELECT employer_id FROM jobs WHERE id=?", (app[0],))
    job = c.fetchone()
    if not job or job[0] != session['user_id']:
        conn.close()
        return "Unauthorized.", 403
    c.execute("UPDATE job_applications SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_status, app_id))
    conn.commit()

    # ---- NOTIFICATION TO APPLICANT ----
    add_notification(app[1], 'application_status', f'Your application for "{app[2]}" status changed to {new_status}', link='/my-applications')
    # --------------------------------

    conn.close()
    return redirect(url_for('view_application', app_id=app_id))


@app.route('/application/<int:app_id>/note', methods=['POST'])
@login_required
def add_application_note(app_id):
    note = request.form.get('note', '').strip()
    if not note:
        return "Note cannot be empty.", 400
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Permission check and get applicant info
    c.execute("""
        SELECT a.job_id, j.employer_id, a.applicant_id, j.title
        FROM job_applications a
        JOIN jobs j ON a.job_id = j.id
        WHERE a.id = ?
    """, (app_id,))
    result = c.fetchone()
    if not result or result[1] != session['user_id']:
        conn.close()
        return "Unauthorized.", 403
    job_title = result[3]
    applicant_id = result[2]

    c.execute("INSERT INTO application_notes (application_id, note, created_by) VALUES (?,?,?)", (app_id, note, session['user_id']))
    conn.commit()

    # ---- NOTIFICATION TO APPLICANT ----
    employer_name = session.get('user_name', 'Employer')
    add_notification(applicant_id, 'application_note', f'{employer_name} added a note on your application for "{job_title}"', link=f'/application/{app_id}')
    # ---------------------------------

    conn.close()
    return redirect(url_for('view_application', app_id=app_id))


@app.route('/job/<int:job_id>/applicants')
@login_required
def job_applicants(job_id):
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT title, employer_id FROM jobs WHERE id=?", (job_id,))
    job = c.fetchone()
    if not job or job[1] != user_id:
        conn.close()
        return "You are not the employer of this job.", 403
    c.execute("""
        SELECT a.id, u.name, a.message, a.status, a.created_at
        FROM job_applications a
        JOIN users u ON a.applicant_id = u.id
        WHERE a.job_id = ?
        ORDER BY a.created_at DESC
    """, (job_id,))
    applicants = c.fetchall()
    conn.close()

    rows = ""
    for app in applicants:
        status_badge = get_application_status_badge(app[3])
        rows += f"""
        <tr>
            <td>{app[1]}</td>
            <td>{app[2] or '-'}</td>
            <td>{status_badge}</td>
            <td>{app[4][:16]}</td>
            <td><a href="/application/{app[0]}" class="btn btn-small">View</a></td>
        </tr>
        """
    if not rows:
        rows = '<tr><td colspan="5">No applications yet.</td></tr>'

    content = f'''
    <div class="card">
        <div class="card-header">Applicants for: {job[0]}</div>
        <table>
            <thead><tr><th>Applicant</th><th>Message</th><th>Status</th><th>Applied</th><th>Action</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
        <a href="/jobs" class="btn btn-outline">Back to Jobs</a>
    </div>
    '''
    return render_user_template(base_template, title="Job Applicants", active_page="jobs", content=content)

@app.route('/job/<int:job_id>')
def job_detail(job_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT j.id, j.title, j.company, j.description, j.location, j.village, j.contact, j.status, j.posted_date, j.job_image,
               u.name as employer_name, u.phone as employer_phone, j.employer_id
        FROM jobs j
        JOIN users u ON j.employer_id = u.id
        WHERE j.id = ?
    """, (job_id,))
    job = c.fetchone()
    conn.close()
    if not job:
        return "Job not found.", 404
    
    job_id, title, company, desc, loc, village, contact, status, posted_date, job_img, employer_name, employer_phone, employer_id = job
    status_class = status.lower()
    location_display = f"{loc}{', ' + village if village else ''}"
    
    # Build apply button (only if user is logged in and not the employer)
    apply_button = ""
    if 'user_id' in session:
        if session['user_id'] == employer_id:
            apply_button = '<p class="alert alert-info">You posted this job.</p>'
        else:
            apply_button = f'<a href="/apply/{job_id}" class="btn">📝 Apply for this Job</a>'
    else:
        apply_button = '<p><a href="/login" class="btn">Login to Apply</a></p>'
    
    content = f'''
    <div class="card">
        <div class="card-header">{title}</div>
        {f'<img src="/static/uploads/{job_img}" class="vendor-img" style="width:100%; max-height:300px; object-fit:cover; border-radius:8px; margin-bottom:15px;">' if job_img else ''}
        <p><strong>Company:</strong> {company or 'N/A'}</p>
        <p><strong>Location:</strong> {location_display}</p>
        <p><strong>Description:</strong> {desc}</p>
        <p><strong>Status:</strong> <span class="badge badge-{status_class}">{status}</span></p>
        <p><strong>Posted:</strong> {posted_date[:10]}</p>
        <p><strong>Employer:</strong> {employer_name} <a href="/messages/{employer_id}" class="btn btn-small btn-whatsapp">💬 Message</a></p>
        <p><strong>Contact:</strong> {employer_phone}</p>
        <hr>
        {apply_button}
        <p><a href="/jobs" class="btn btn-outline">← Back to Jobs</a></p>
    </div>
    '''
    return render_user_template(base_template, title=f"Job: {title}", active_page="jobs", content=content)


# ============================================================
# IN-APP MESSAGING ROUTES
# ============================================================

@app.route('/messages')
@login_required
def messages_inbox():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Get all unique conversation partners
    c.execute("""
        SELECT DISTINCT
            CASE WHEN sender_id = ? THEN receiver_id ELSE sender_id END as partner_id
        FROM messages
        WHERE sender_id = ? OR receiver_id = ?
    """, (user_id, user_id, user_id))
    partners = [row[0] for row in c.fetchall()]
    convos = []
    for partner in partners:
        c.execute("""
            SELECT sender_id, receiver_id, message, is_read, created_at
            FROM messages
            WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)
            ORDER BY created_at DESC LIMIT 1
        """, (partner, user_id, user_id, partner))
        last_msg = c.fetchone()
        if last_msg:
            name = get_user_name(partner)
            # Count unread messages for this conversation
            c.execute("""
                SELECT COUNT(*) FROM messages
                WHERE sender_id=? AND receiver_id=? AND is_read=0
            """, (partner, user_id))
            unread_count = c.fetchone()[0]
            convos.append({
                'partner_id': partner,
                'name': name,
                'last_message': last_msg[2],
                'created_at': last_msg[4],
                'unread_count': unread_count
            })
    # Sort by latest message
    convos.sort(key=lambda x: x['created_at'], reverse=True)
    conn.close()

    rows = ""
    for c in convos:
        unread_badge = f'<span class="badge" style="background:#dc3545; color:white;">{c["unread_count"]}</span>' if c['unread_count'] > 0 else ''
        rows += f"""
        <div class="provider-card" onclick="window.location='/messages/{c['partner_id']}'" style="cursor:pointer;">
            <div class="provider-info">
                <h3>{c['name']} {unread_badge}</h3>
                <p>{c['last_message'][:100]}</p>
                <small>{c['created_at'][:16]}</small>
            </div>
        </div>
        """
    if not rows:
        rows = "<p>No messages yet.</p>"

    content = f'''
    <div class="card">
        <div class="card-header">📨 Inbox <span class="badge badge-available" style="background:#28a745; color:white;" id="inboxUnreadBadge">{sum(c['unread_count'] for c in convos)} unread</span></div>
        {rows}
    </div>
    <script>
        // Refresh inbox unread count every 10 seconds
        setInterval(function() {{
            fetch('/api/unread-count')
                .then(r => r.json())
                .then(data => {{
                    const badge = document.getElementById('inboxUnreadBadge');
                    if (badge) badge.textContent = data.count + ' unread';
                }});
        }}, 10000);
    </script>
    '''
    return render_user_template(base_template, title="Messages", active_page="messages", content=content)


@app.route('/messages/<int:user_id>', methods=['GET', 'POST'])
@login_required
def message_conversation(user_id):
    current_user = session['user_id']
    if current_user == user_id:
        return "You cannot message yourself.", 400

    # Mark messages as read
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE messages SET is_read = 1
        WHERE sender_id = ? AND receiver_id = ?
    """, (user_id, current_user))
    conn.commit()

    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if message:
            c.execute("""
                INSERT INTO messages (sender_id, receiver_id, message)
                VALUES (?,?,?)
            """, (current_user, user_id, message))
            conn.commit()
            add_notification(user_id, 'message', f'New message from {session["user_name"]}')
        return redirect(url_for('message_conversation', user_id=user_id))

    # Fetch conversation
    c.execute("""
        SELECT sender_id, message, created_at
        FROM messages
        WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)
        ORDER BY created_at ASC
    """, (current_user, user_id, user_id, current_user))
    msgs = c.fetchall()
    conn.close()

    partner_name = get_user_name(user_id)

    # Build chat HTML (messages will be rendered inside a container)
    content = f'''
    <div class="card">
        <div class="card-header">💬 {partner_name} <a href="/messages" class="btn btn-small btn-outline">← Back</a></div>
        <div id="chatContainer" style="height:400px; overflow-y:auto; padding:10px; background:var(--bg); border-radius:8px; margin-bottom:15px;">
            {''.join([f'''
            <div style="text-align:{"right" if msg[0]==current_user else "left"}; margin:5px 0;">
                <div style="display:inline-block; background:{"#f5af19" if msg[0]==current_user else "var(--card-bg)"}; color:{"white" if msg[0]==current_user else "var(--text)"}; padding:10px 15px; border-radius:15px; max-width:70%;">
                    {msg[1]}
                    <div style="font-size:0.7rem; opacity:0.7;">{msg[2][:16]}</div>
                </div>
            </div>
            ''' for msg in msgs])}
        </div>
        <form method="POST" style="display:flex; gap:10px;" id="messageForm">
            <input type="text" name="message" placeholder="Type a message..." required style="flex:1;">
            <button type="submit" class="btn">Send</button>
        </form>
    </div>
    <script>
        // Poll for new messages every 3 seconds
        const chatContainer = document.getElementById('chatContainer');
        const form = document.getElementById('messageForm');
        let lastMessageTime = document.querySelector('#chatContainer > div:last-child')?.querySelector('div:last-child')?.textContent || '';

        function loadNewMessages() {{
            fetch('/api/messages/{user_id}?since=' + encodeURIComponent(lastMessageTime))
                .then(r => r.json())
                .then(data => {{
                    if (data.messages && data.messages.length > 0) {{
                        data.messages.forEach(msg => {{
                            const div = document.createElement('div');
                            const align = msg.sender == {current_user} ? 'right' : 'left';
                            const bg = msg.sender == {current_user} ? '#f5af19' : 'var(--card-bg)';
                            const color = msg.sender == {current_user} ? 'white' : 'var(--text)';
                            div.style.cssText = `text-align:${{align}}; margin:5px 0;`;
                            div.innerHTML = `
                                <div style="display:inline-block; background:${{bg}}; color:${{color}}; padding:10px 15px; border-radius:15px; max-width:70%;">
                                    ${{msg.text}}
                                    <div style="font-size:0.7rem; opacity:0.7;">${{msg.time.slice(0,16)}}</div>
                                </div>
                            `;
                            chatContainer.appendChild(div);
                            // Update last message time
                            if (msg.time > lastMessageTime) lastMessageTime = msg.time;
                        }});
                        // Scroll to bottom
                        chatContainer.scrollTop = chatContainer.scrollHeight;
                    }}
                }});
        }}

        // Initial poll, then every 3 seconds
        setInterval(loadNewMessages, 3000);

        // Auto-scroll to bottom on load
        chatContainer.scrollTop = chatContainer.scrollHeight;
    </script>
    '''
    return render_user_template(base_template, title=f"Chat with {partner_name}", active_page="messages", content=content)

# ============================================================
# PWA ROUTES
# ============================================================
@app.route('/manifest.json')
def manifest():
    return send_from_directory(BASE_DIR, 'manifest.json', mimetype='application/json')

@app.route('/service-worker.js')
def service_worker():
    return send_from_directory(BASE_DIR, 'service-worker.js', mimetype='application/javascript')

# ---- API: Unread count ----
@app.route('/api/unread-count')
@login_required
def api_unread_count():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages WHERE receiver_id=? AND is_read=0", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return {'count': count}

# ---- API: New messages (polling) ----
@app.route('/api/messages/<int:user_id>')
@login_required
def api_messages(user_id):
    current_user = session['user_id']
    since = request.args.get('since', '')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if since:
        c.execute("""
            SELECT sender_id, message, created_at
            FROM messages
            WHERE ((sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?))
            AND created_at > ?
            ORDER BY created_at ASC
        """, (current_user, user_id, user_id, current_user, since))
    else:
        c.execute("""
            SELECT sender_id, message, created_at
            FROM messages
            WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)
            ORDER BY created_at ASC
        """, (current_user, user_id, user_id, current_user))
    msgs = c.fetchall()
    conn.close()
    return {'messages': [{'sender': m[0], 'text': m[1], 'time': m[2]} for m in msgs]}

@app.route('/download/<filename>')
@login_required
def download_file(filename):
    """Download an uploaded file (CV/attachment)."""
    # Check if file exists
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(file_path):
        return "File not found.", 404

    # Optional: Check if the user has permission to download this file
    # Only allow if user is the applicant or the employer of the job
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT a.applicant_id, j.employer_id
        FROM job_applications a
        JOIN jobs j ON a.job_id = j.id
        WHERE a.attachment = ?
    """, (filename,))
    result = c.fetchone()
    conn.close()
    if result:
        applicant_id, employer_id = result
        user_id = session['user_id']
        if user_id != applicant_id and user_id != employer_id:
            return "You do not have permission to download this file.", 403
    # If not found in job_applications, allow download anyway (fallback)

    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/delete-profile', methods=['POST'])
@login_required
def delete_profile():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM providers WHERE user_id=?", (user_id,))
    provider = c.fetchone()
    if not provider:
        conn.close()
        return "You don't have a freelancer profile.", 404
    c.execute("DELETE FROM providers WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    return redirect('/dashboard')

@app.route('/delete-vendor-profile', methods=['POST'])
@login_required
def delete_vendor_profile():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM vendors WHERE user_id=?", (user_id,))
    vendor = c.fetchone()
    if not vendor:
        conn.close()
        return "You don't have a vendor profile.", 404
    c.execute("DELETE FROM vendors WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    return redirect('/dashboard')

@app.route('/delete-job/<int:job_id>', methods=['POST'])
@login_required
def delete_job(job_id):
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT employer_id FROM jobs WHERE id=?", (job_id,))
    job = c.fetchone()
    if not job:
        conn.close()
        return "Job not found.", 404
    if job[0] != user_id:
        conn.close()
        return "You are not the employer of this job.", 403
    c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    conn.commit()
    conn.close()
    return redirect('/dashboard')


# ============================================================
# RUN APP
# ============================================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
