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

# ============================================================
# PAGE FRAGMENTS (Unchanged from your PythonAnywhere code)
# ============================================================
home_page = base_template.replace("{title}", "Home").replace("{active_page}", "home").replace("{content}", """
    <div class="hero">
        <h1>Get Work Done – or Get Paid</h1>
        <p>Uganda’s freelance marketplace. Connect with trusted skilled workers near you.</p>
        <div style="margin-top:20px;">
            <a href="/offer-skill" class="btn" style="margin-right:10px;">Offer Your Skill</a>
            <a href="/post-job" class="btn btn-outline" style="border-color:white; color:white;">Post a Job</a>
        </div>
        <div class="category-chips">
            <span style="color:white; margin-right:8px;">Popular:</span>
            <a href="/list?search=Boda+Rider" class="chip">Boda Rider</a>
            <a href="/list?search=Maid" class="chip">Maid</a>
            <a href="/list?search=Plumbing" class="chip">Plumbing</a>
            <a href="/list?search=Construction" class="chip">Construction</a>
            <a href="/list?search=Cooking" class="chip">Cooking</a>
            <a href="/list?search=Driver" class="chip">Driver</a>
        </div>
    </div>
    <div style="display:flex; gap:15px; margin-bottom:20px; text-align:center;">
        <div class="card" style="flex:1;">
            <h3>{provider_count}</h3>
            <small>Skilled Workers</small>
        </div>
        <div class="card" style="flex:1;">
            <h3>{open_jobs}</h3>
            <small>Open Jobs</small>
        </div>
    </div>
    <div class="card">
        <div class="card-header">How It Works</div>
        <p>1️⃣ <strong>Find Skills</strong> – Browse verified workers in your area.</p>
        <p>2️⃣ <strong>Post a Job</strong> – Describe what you need done.</p>
        <p>3️⃣ <strong>Connect</strong> – Chat on WhatsApp and get it done!</p>
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

dashboard_template = base_template.replace("{title}", "Dashboard").replace("{active_page}", "dashboard").replace("{content}", "{dashboard_content}")

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
            <label>Status</label>
            <select name="status">
                {status_options}
            </select>
            <button type="submit" class="btn" style="margin-top:20px; width:100%;">Save Vendor Profile</button>
        </form>
    </div>
    <script>
    // Client‑side image resizer – compresses images before upload for lightning speed
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
# ROUTES (Using DB_PATH instead of hardcoded path)
# ============================================================

@app.route('/')
def home():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM providers")
    provider_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM jobs WHERE status='Open'")
    open_jobs = c.fetchone()[0]
    conn.close()
    return render_template_string(home_page.replace("{provider_count}", str(provider_count)).replace("{open_jobs}", str(open_jobs)))

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
            conn.close()
            add_notification(user_id, 'email', f'Welcome {name}! Your RockabyConnect account is ready.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return "Phone number already registered. <a href='/login'>Login</a>"
    return render_template_string(signup_page)

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
    return render_template_string(login_page)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/edit-name')
@login_required
def edit_name():
    return render_template_string(edit_name_page.replace("{current_name}", session['user_name']))

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
    conn.execute("PRAGMA busy_timeout = 5000;")
    c = conn.cursor()

    c.execute("SELECT * FROM providers WHERE user_id=?", (user_id,))
    provider = c.fetchone()

    c.execute("SELECT * FROM vendors WHERE user_id=?", (user_id,))
    vendor = c.fetchone()

    c.execute("SELECT id, title, status FROM jobs WHERE employer_id=? ORDER BY id DESC", (user_id,))
    jobs = c.fetchall()
    conn.close()

    profile_section = ""
    if provider:
        pid, _, skills, district, village, bio, pic, status, featured, featured_expiry = provider
        status_class = status.lower().replace(' ', '-')
        location = f"{district}{', ' + village if village else ''}"
        profile_section = f"""
            <div class="card">
                <div class="card-header">My Freelancer Profile</div>
                <p><strong>Skills:</strong> {skills}</p>
                <p><strong>Location:</strong> {location}</p>
                <p><strong>Status:</strong> <span class="badge badge-{status_class}">{status}</span></p>
                <div style="display:flex; gap:10px; margin-top:15px;">
                    <a href="/edit-profile" class="btn btn-small">Edit Profile</a>
                    <a href="/boost" class="btn btn-small" style="background:var(--primary-dark);">Boost Profile</a>
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

    vendor_section = ""
    if vendor:
        vid, _, bname, district, village, landmark, bio, vimg, vimg2, vimg3, vstatus, vfeatured, vexpiry = vendor
        vstatus_class = vstatus.lower()
        location = f"{district}{', ' + village if village else ''}{', ' + landmark if landmark else ''}"
        vendor_section = f"""
            <div class="card">
                <div class="card-header">My Vendor Profile</div>
                <p><strong>Business:</strong> {bname}</p>
                <p><strong>Location:</strong> {location}</p>
                <p><strong>Status:</strong> <span class="badge badge-{vstatus_class}">{vstatus}</span></p>
                <div style="display:flex; gap:10px; margin-top:15px;">
                    <a href="/edit-vendor-profile" class="btn btn-small">Edit Vendor Profile</a>
                    <a href="/boost-vendor" class="btn btn-small" style="background:var(--primary-dark);">Boost Vendor</a>
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

    jobs_html = ""
    if jobs:
        for job in jobs:
            jid, title, status = job
            badge_class = 'open' if status == 'Open' else ('taken' if status == 'Taken' else 'closed')
            jobs_html += f"""
                <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid var(--border);">
                    <span>{title} <span class="badge badge-{badge_class}">{status}</span></span>
                    <div style="display:flex; gap:5px;">
                        <a href="/edit-job/{jid}" class="btn btn-small btn-outline">Edit</a>
                        <a href="/boost-job/{jid}" class="btn btn-small" style="background:var(--primary-dark);">Boost</a>
                    </div>
                </div>
            """
    else:
        jobs_html = "<p>No jobs posted yet.</p>"

    dashboard_content = f"""
        <div class="card">
            <h2>Welcome, {session['user_name']}!</h2>
            <p><a href="/edit-name" style="font-size:0.85rem; color:var(--primary-dark);">Edit my name</a></p>
            <p style="color:#666;">Manage your freelance presence, vendor profile, and job postings.</p>
        </div>
        {profile_section}
        {vendor_section}
        <div class="card">
            <div class="card-header">My Job Postings</div>
            {jobs_html}
            <a href="/post-job" class="btn" style="margin-top:10px;">Post a New Job</a>
        </div>
    """
    return render_template_string(dashboard_template.replace("{dashboard_content}", dashboard_content))

# ---------- Freelancer Profile (create/edit) ----------
@app.route('/create-profile', methods=['GET', 'POST'])
@login_required
def create_profile():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM providers WHERE user_id=?", (user_id,))
    if c.fetchone():
        conn.close()
        return redirect('/edit-profile')
    conn.close()

    if request.method == 'POST':
        skills = request.form['skills'].strip()
        district = request.form['district'].strip()
        village = request.form.get('village', '').strip()
        bio = request.form.get('bio', '').strip()
        status = request.form.get('status', 'Available')
        file = request.files.get('profile_pic')
        filename = None
        if file and allowed_file(file.filename):
            filename = save_resized_image(file, max_width=800)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO providers (user_id, skills, district, village, bio, profile_pic, status) VALUES (?,?,?,?,?,?,?)",
                  (user_id, skills, district, village, bio, filename, status))
        conn.commit()
        conn.close()
        return redirect('/dashboard')

    form_html = profile_form_template.replace("{form_title}", "Create Your Freelancer Profile")
    form_html = form_html.replace("{skills}", "")
    form_html = form_html.replace("{skill_suggestions}", ', '.join(SKILL_SUGGESTIONS[:10]) + ', ...')
    form_html = form_html.replace("{district}", "").replace("{village}", "").replace("{bio}", "")
    status_options = ''.join([f'<option value="{s}">{s}</option>' for s in FREELANCER_STATUSES])
    form_html = form_html.replace("{status_options}", status_options)
    return render_template_string(form_html)

@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT skills, district, village, bio, profile_pic, status FROM providers WHERE user_id=?", (user_id,))
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
        if file and allowed_file(file.filename):
            filename = save_resized_image(file, max_width=800)
            c.execute("UPDATE providers SET skills=?, district=?, village=?, bio=?, profile_pic=?, status=? WHERE user_id=?",
                      (skills, district, village, bio, filename, status, user_id))
        else:
            c.execute("UPDATE providers SET skills=?, district=?, village=?, bio=?, status=? WHERE user_id=?",
                      (skills, district, village, bio, status, user_id))
        conn.commit()
        conn.close()
        return redirect('/dashboard')

    skills, district, village, bio, pic, status = provider
    form_html = profile_form_template.replace("{form_title}", "Edit Your Freelancer Profile")
    form_html = form_html.replace("{skills}", skills or '')
    form_html = form_html.replace("{skill_suggestions}", ', '.join(SKILL_SUGGESTIONS[:10]) + ', ...')
    form_html = form_html.replace("{district}", district or '')
    form_html = form_html.replace("{village}", village or '')
    form_html = form_html.replace("{bio}", bio or '')
    status_options = ''.join([f'<option value="{s}" {"selected" if s==status else ""}>{s}</option>' for s in FREELANCER_STATUSES])
    form_html = form_html.replace("{status_options}", status_options)
    conn.close()
    return render_template_string(form_html)

# ---------- Vendor Profile (create/edit) ----------
@app.route('/create-vendor-profile', methods=['GET', 'POST'])
@login_required
def create_vendor_profile():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
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
                filenames[idx] = save_resized_image(file, max_width=800)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO vendors (user_id, business_name, district, village, landmark, bio, vendor_image, vendor_image2, vendor_image3, status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (user_id, business_name, district, village, landmark, bio, filenames[0], filenames[1], filenames[2], status))
        conn.commit()
        conn.close()
        return redirect('/dashboard')

    form = vendor_form_template.replace("{form_title}", "Create Your Vendor Profile")
    form = form.replace("{business_name}", "").replace("{district}", "").replace("{village}", "")
    form = form.replace("{landmark}", "").replace("{bio}", "")
    status_options = ''.join([f'<option value="{s}">{s}</option>' for s in VENDOR_STATUSES])
    form = form.replace("{status_options}", status_options)
    return render_template_string(form)

@app.route('/edit-vendor-profile', methods=['GET', 'POST'])
@login_required
def edit_vendor_profile():
    user_id = session['user_id']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT business_name, district, village, landmark, bio, vendor_image, vendor_image2, vendor_image3, status FROM vendors WHERE user_id=?", (user_id,))
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
                current_images[idx] = save_resized_image(file, max_width=800)

        c.execute("UPDATE vendors SET business_name=?, district=?, village=?, landmark=?, bio=?, vendor_image=?, vendor_image2=?, vendor_image3=?, status=? WHERE user_id=?",
                  (business_name, district, village, landmark, bio, current_images[0], current_images[1], current_images[2], status, user_id))
        conn.commit()
        conn.close()
        return redirect('/dashboard')

    bname, district, village, landmark, bio, img, img2, img3, status = vendor
    form = vendor_form_template.replace("{form_title}", "Edit Your Vendor Profile")
    form = form.replace("{business_name}", bname or '')
    form = form.replace("{district}", district or '')
    form = form.replace("{village}", village or '')
    form = form.replace("{landmark}", landmark or '')
    form = form.replace("{bio}", bio or '')
    status_options = ''.join([f'<option value="{s}" {"selected" if s==status else ""}>{s}</option>' for s in VENDOR_STATUSES])
    form = form.replace("{status_options}", status_options)
    conn.close()
    return render_template_string(form)

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
    return render_template_string(base_template.replace("{title}", "Boost Vendor").replace("{active_page}", "dashboard").replace("{content}", """
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
    """))

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
    return render_template_string(base_template.replace("{title}", "Boost Submitted").replace("{active_page}", "dashboard").replace("{content}", """
        <div class="card"><h2>Vendor Boost Submitted</h2><p>We'll verify and activate soon.</p><a href="/dashboard" class="btn">Back</a></div>
    """))

# ---------- Vendor Public Listing & Detail ----------
@app.route('/vendors')
def list_vendors():
    logged_in = 'user_id' in session
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000;")
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
    return render_template_string(vendor_list_page.replace("{cards}", cards))

@app.route('/vendor/<int:vendor_id>')
def vendor_detail(vendor_id):
    logged_in = 'user_id' in session
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT v.business_name, v.district, v.village, v.landmark, v.bio, v.vendor_image, v.vendor_image2, v.vendor_image3, v.status, v.featured, v.featured_expiry, u.phone
        FROM vendors v JOIN users u ON v.user_id = u.id WHERE v.id=?
    """, (vendor_id,))
    v = c.fetchone()
    if not v:
        conn.close()
        return "Vendor not found.", 404
    bname, district, village, landmark, bio, img, img2, img3, status, featured, expiry, phone = v
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

    extra_images = ""
    if img2 or img3:
        extra_images = '<div class="vendor-img-gallery">'
        if img2:
            extra_images += f'<img src="/static/uploads/{img2}" alt="Additional photo">'
        if img3:
            extra_images += f'<img src="/static/uploads/{img3}" alt="Additional photo">'
        extra_images += '</div>'

    detail_html = vendor_detail_template
    detail_html = detail_html.replace("{business_name}", bname)
    detail_html = detail_html.replace("{img_url}", img_url)
    detail_html = detail_html.replace("{extra_images}", extra_images)
    detail_html = detail_html.replace("{district}", district)
    detail_html = detail_html.replace("{village_display}", village_display)
    detail_html = detail_html.replace("{landmark_display}", landmark_display)
    detail_html = detail_html.replace("{bio}", bio or 'No description')
    detail_html = detail_html.replace("{status_class}", status_class)
    detail_html = detail_html.replace("{status}", status)
    detail_html = detail_html.replace("{feat}", feat)
    detail_html = detail_html.replace("{contact_display}", contact_display)
    conn.close()
    return render_template_string(detail_html)

# ---------- Boost & Admin ----------
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
    return render_template_string(base_template.replace("{title}", "Boost Your Profile").replace("{active_page}", "dashboard").replace("{content}", """
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
    """))

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
    return render_template_string(base_template.replace("{title}", "Boost Submitted").replace("{active_page}", "dashboard").replace("{content}", """
        <div class="card"><h2>Boost Request Submitted</h2><p>We'll verify and activate soon.</p><a href="/dashboard" class="btn">Back</a></div>
    """))

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
    return render_template_string(base_template.replace("{title}", "Boost Job").replace("{active_page}", "dashboard").replace("{content}", f"""
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
    """))

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
    return render_template_string(base_template.replace("{title}", "Boost Submitted").replace("{active_page}", "dashboard").replace("{content}", """
        <div class="card"><h2>Job Boost Submitted</h2><p>We'll verify and activate soon.</p><a href="/dashboard" class="btn">Back</a></div>
    """))

# Admin Panel
@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect('/admin')
        else:
            return render_template_string(base_template.replace("{title}", "Admin Login").replace("{active_page}", "").replace("{content}", """
                <div class="card"><h2>Admin Login</h2><form method="POST"><label>Password</label><input type="password" name="password" required><button type="submit" class="btn">Login</button></form><p style="color:red;">Wrong password.</p></div>
            """))
    if not session.get('admin'):
        return render_template_string(base_template.replace("{title}", "Admin Login").replace("{active_page}", "").replace("{content}", """
            <div class="card"><h2>Admin Login</h2><form method="POST"><label>Password</label><input type="password" name="password" required><button type="submit" class="btn">Login</button></form></div>
        """))

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000;")
    c = conn.cursor()

    action = request.args.get('action')
    req_id = request.args.get('req_id')
    if action == 'approve' and req_id:
        req_id = int(req_id)
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
            conn.close()
            add_notification(user_id, 'sms', 'Your boost has been approved and is now live!')
        else:
            conn.close()
        return redirect('/admin')

    if action == 'reject' and req_id:
        req_id = int(req_id)
        c.execute("UPDATE boost_requests SET status='rejected' WHERE id=?", (req_id,))
        conn.commit()
        conn.close()
        return redirect('/admin')

    today = date.today().isoformat()
    c.execute("UPDATE providers SET featured=0 WHERE featured=1 AND featured_expiry IS NOT NULL AND featured_expiry < ?", (today,))
    c.execute("UPDATE jobs SET featured=0 WHERE featured=1 AND featured_expiry IS NOT NULL AND featured_expiry < ?", (today,))
    c.execute("UPDATE vendors SET featured=0 WHERE featured=1 AND featured_expiry IS NOT NULL AND featured_expiry < ?", (today,))
    conn.commit()

    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM providers")
    total_providers = c.fetchone()[0]
    c.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
    job_stats = dict(c.fetchall())
    c.execute("SELECT COUNT(*) FROM boost_requests WHERE status='pending'")
    pending_boosts = c.fetchone()[0]
    conn.close()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000;")
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
        <tr><td>{rid}</td><td>{name}<br><small>{phone}</small></td><td>{trans}</td><td>{plan} days</td><td>{btype}</td><td>{rdate[:16] if rdate else ''}</td>
        <td><a href="/admin?action=approve&req_id={rid}" class="btn btn-small" style="background:var(--primary);">Approve</a> <a href="/admin?action=reject&req_id={rid}" class="btn btn-small btn-danger">Reject</a></td></tr>"""
    if not rows:
        rows = "<tr><td colspan='7'>No pending requests.</td></tr>"

    admin_content = f"""
        <div class="card">
            <h3>Dashboard Stats</h3>
            <table>
                <tr><td>Total Users</td><td>{total_users}</td></tr>
                <tr><td>Total Providers</td><td>{total_providers}</td></tr>
                <tr><td>Open Jobs</td><td>{job_stats.get('Open', 0)}</td></tr>
                <tr><td>Taken Jobs</td><td>{job_stats.get('Taken', 0)}</td></tr>
                <tr><td>Closed Jobs</td><td>{job_stats.get('Closed', 0)}</td></tr>
                <tr><td>Pending Boosts</td><td>{pending_boosts}</td></tr>
            </table>
        </div>
        <div class="card">
            <div class="card-header">Pending Boost Requests</div>
            <table>
                <tr><th>ID</th><th>User</th><th>Transaction</th><th>Plan</th><th>Type</th><th>Date</th><th>Action</th></tr>
                {rows}
            </table>
            <p style="margin-top:15px;">
                <a href="/admin/stats" class="btn btn-outline">📊 Statistics</a>
                <a href="/admin/logout">Logout</a>
            </p>
        </div>
    """
    return render_template_string(base_template.replace("{title}", "Admin").replace("{active_page}", "").replace("{content}", admin_content))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin')

# Admin stats
@app.route('/admin/stats')
def admin_stats():
    if not session.get('admin'):
        return redirect('/admin')

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000;")
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

    revenue = 0
    c.execute("SELECT plan FROM boost_requests WHERE status='approved'")
    for row in c.fetchall():
        plan = int(row[0])
        if plan == 7:
            revenue += 5000
        elif plan == 30:
            revenue += 15000

    c.execute("""
        SELECT date(posted_date) as day, COUNT(*) as count
        FROM jobs WHERE posted_date >= date('now', '-7 days')
        GROUP BY day ORDER BY day
    """)
    daily_jobs = c.fetchall()
    last_7_days = [(date.today() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    day_counts = defaultdict(int, {day: cnt for day, cnt in daily_jobs})

    c.execute("SELECT skills FROM providers WHERE skills IS NOT NULL AND skills != ''")
    skill_rows = c.fetchall()
    skill_counter = defaultdict(int)
    for (skills_str,) in skill_rows:
        for skill in skills_str.split(','):
            skill = skill.strip().title()
            if skill:
                skill_counter[skill] += 1
    top_skills = sorted(skill_counter.items(), key=lambda x: x[1], reverse=True)[:5]

    recent = []
    c.execute("SELECT name, 'Registered' as event, id as ref_id, rowid as ts FROM users ORDER BY rowid DESC LIMIT 5")
    for row in c.fetchall():
        recent.append(('user', row[0], row[1], row[2], row[3]))
    c.execute("SELECT title, 'Posted Job', id, posted_date FROM jobs ORDER BY id DESC LIMIT 5")
    for row in c.fetchall():
        recent.append(('job', row[0], row[1], row[2], row[3]))
    c.execute("SELECT u.name, 'Reviewed', r.id, r.created_at FROM reviews r JOIN users u ON r.reviewer_id = u.id ORDER BY r.id DESC LIMIT 5")
    for row in c.fetchall():
        recent.append(('review', row[0], row[1], row[2], row[3]))
    c.execute("SELECT u.name, 'Boost Request', br.id, br.request_date FROM boost_requests br JOIN users u ON br.user_id = u.id ORDER BY br.id DESC LIMIT 5")
    for row in c.fetchall():
        recent.append(('boost', row[0], row[1], row[2], row[3]))
    c.execute("SELECT business_name, 'Vendor Registered', id, rowid FROM vendors ORDER BY id DESC LIMIT 5")
    for row in c.fetchall():
        recent.append(('vendor', row[0], row[1], row[2], row[3]))
    recent.sort(key=lambda x: str(x[3]) if x[3] else '', reverse=True)
    recent = recent[:10]

    conn.close()

    max_count = max(day_counts.values()) if day_counts.values() else 1
    bar_html = ""
    for day in last_7_days:
        cnt = day_counts[day]
        percent = (cnt / max_count * 100) if max_count else 0
        bar_html += f"""
        <div style="display:flex; align-items:center; margin:5px 0;">
            <div style="width:80px; font-size:0.8rem;">{day[5:]}</div>
            <div style="flex:1; background:#eee; border-radius:4px; height:20px;">
                <div style="width:{percent}%; background:var(--primary); height:100%; border-radius:4px;"></div>
            </div>
            <div style="width:30px; font-size:0.8rem; margin-left:5px;">{cnt}</div>
        </div>"""

    top_skills_html = "".join(f"<tr><td>{skill}</td><td>{cnt}</td></tr>" for skill, cnt in top_skills) or "<tr><td colspan='2'>No skills yet.</td></tr>"
    recent_html = "".join(f"<tr><td>{name}</td><td>{event}</td><td>{str(ts)[:16] if ts else ''}</td></tr>" for (etype, name, event, ref_id, ts) in recent) or "<tr><td colspan='3'>No activity yet.</td></tr>"

    stats_content = f"""
    <div class="card">
        <h2>📊 Platform Statistics</h2>
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap:10px; margin-top:15px;">
            <div class="card" style="text-align:center;"><h3>{total_users}</h3><small>Total Users</small></div>
            <div class="card" style="text-align:center;"><h3>{total_providers}</h3><small>Providers</small></div>
            <div class="card" style="text-align:center;"><h3>{total_vendors}</h3><small>Vendors</small></div>
            <div class="card" style="text-align:center;"><h3>{open_jobs}</h3><small>Open Jobs</small></div>
            <div class="card" style="text-align:center;"><h3>{taken_jobs}</h3><small>Taken Jobs</small></div>
            <div class="card" style="text-align:center;"><h3>{closed_jobs}</h3><small>Closed Jobs</small></div>
            <div class="card" style="text-align:center;"><h3>{open_vendors}</h3><small>Open Vendors</small></div>
            <div class="card" style="text-align:center;"><h3>{closed_vendors}</h3><small>Closed Vendors</small></div>
            <div class="card" style="text-align:center;"><h3>{away_vendors}</h3><small>Away Vendors</small></div>
            <div class="card" style="text-align:center;"><h3>{pending_boosts}</h3><small>Pending Boosts</small></div>
            <div class="card" style="text-align:center;"><h3>{approved_boosts}</h3><small>Approved Boosts</small></div>
            <div class="card" style="text-align:center;"><h3>UGX {revenue:,}</h3><small>Est. Revenue</small></div>
        </div>
    </div>

    <div class="card">
        <div class="card-header">📅 Jobs Posted (Last 7 Days)</div>
        {bar_html}
    </div>

    <div class="card">
        <div class="card-header">💪 Top 5 Skills</div>
        <table><tr><th>Skill</th><th>Providers</th></tr>{top_skills_html}</table>
    </div>

    <div class="card">
        <div class="card-header">🕒 Recent Activity</div>
        <table><tr><th>User/Name</th><th>Action</th><th>Time</th></tr>{recent_html}</table>
    </div>
    <p style="margin-top:15px;"><a href="/admin" class="btn btn-outline">Back to Boosts</a> <a href="/admin/logout" class="btn btn-small btn-danger">Logout</a></p>
    """
    return render_template_string(base_template.replace("{title}", "Admin Stats").replace("{active_page}", "").replace("{content}", stats_content))

# ---------- Job posting, editing, public job listing, provider detail, reviews ----------
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
        filename = None
        if file and allowed_file(file.filename):
            filename = save_resized_image(file, max_width=800)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO jobs (employer_id, title, company, description, location, village, contact, status, job_image) VALUES (?,?,?,?,?,?,?,'Open',?)",
                  (session['user_id'], title, company, description, location, village, contact, filename))
        conn.commit()
        conn.close()
        return redirect('/dashboard')
    form = job_form_template.replace("{job_form_title}", "Post a Job").replace("{form_header}", "Post a New Job")
    form = form.replace("{title_val}", "").replace("{company_val}", "").replace("{description_val}", "")
    form = form.replace("{location_val}", "").replace("{village_val}", "").replace("{contact_val}", "")
    form = form.replace("{submit_button}", "Post Job")
    return render_template_string(form)

@app.route('/edit-job/<int:job_id>', methods=['GET', 'POST'])
@login_required
def edit_job(job_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT title, company, description, location, village, contact, status, employer_id, job_image FROM jobs WHERE id=?", (job_id,))
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
        filename = job[8]
        if file and allowed_file(file.filename):
            filename = save_resized_image(file, max_width=800)
        c.execute("UPDATE jobs SET title=?, company=?, description=?, location=?, village=?, contact=?, status=?, job_image=? WHERE id=?",
                  (title, company, description, location, village, contact, status, filename, job_id))
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
    return render_template_string(form)

@app.route('/list')
def list_providers():
    logged_in = 'user_id' in session
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000;")
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
    return render_template_string(list_page.replace("{cards}", cards_html))

@app.route('/jobs')
def list_jobs():
    logged_in = 'user_id' in session
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA busy_timeout = 5000;")
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute("UPDATE jobs SET featured=0 WHERE featured=1 AND featured_expiry IS NOT NULL AND featured_expiry < ?", (today,))
    conn.commit()
    c.execute("""
        SELECT j.title, j.company, j.description, j.location, j.village, j.contact, j.status, j.posted_date, j.job_image, j.featured, j.featured_expiry
        FROM jobs j ORDER BY CASE WHEN j.featured = 1 AND (j.featured_expiry IS NULL OR j.featured_expiry >= date('now')) THEN 0 ELSE 1 END, j.id DESC
    """)
    jobs = c.fetchall()
    conn.close()
    jobs_html = ""
    for j in jobs:
        title, company, desc, loc, village, contact, status, posted_date, image, featured, expiry = j
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
        jobs_html += f"""
        <div class="job-card">
            {img_tag}
            <div class="job-info">
                <h3>{title} <span class="badge badge-{badge_class}">{status}</span> {feat_badge}</h3>
                <p class="meta">{company or 'N/A'} · {location_display} · {posted_date[:10] if posted_date else ''}</p>
                <p>{desc}</p>
                {contact_display}
            </div>
        </div>"""
    if not jobs_html:
        jobs_html = "<p>No jobs yet.</p>"
    return render_template_string(job_list_page.replace("{jobs_html}", jobs_html))

@app.route('/provider/<int:provider_id>')
def provider_detail(provider_id):
    logged_in = 'user_id' in session
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT p.id, u.name, p.skills, p.district, p.village, p.bio, p.profile_pic, p.status, p.featured, p.featured_expiry, u.phone
        FROM providers p JOIN users u ON p.user_id = u.id WHERE p.id=?
    """, (provider_id,))
    provider = c.fetchone()
    if not provider:
        conn.close()
        return "Provider not found.", 404
    pid, name, skills, district, village, bio, pic, status, featured, expiry, phone = provider
    status_class = status.lower().replace(' ', '-')
    village_display = f", {village}" if village else ""
    img_url = f"/static/uploads/{pic}" if pic else "https://via.placeholder.com/120"
    active_featured = is_featured_now(featured, expiry)
    feat = '<span class="badge badge-available">FEATURED</span>' if active_featured else ''
    if logged_in:
        contact_display = f'<p><strong>Contact:</strong> {phone} <a href="{whatsapp_link(phone)}" target="_blank" class="btn btn-whatsapp btn-small">WhatsApp</a></p>'
    else:
        contact_display = '<p><strong>Contact:</strong> <a href="/login">Sign in to view</a></p>'
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
    return render_template_string(detail_html)

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

# ============================================================
# PWA ROUTES (serve static files from the root directory)
# ============================================================
@app.route('/manifest.json')
def manifest():
    # Serve the manifest.json file from the same directory as flask_app.py
    return send_from_directory(BASE_DIR, 'manifest.json', mimetype='application/json')

@app.route('/service-worker.js')
def service_worker():
    # Serve the service-worker.js file from the same directory as flask_app.py
    return send_from_directory(BASE_DIR, 'service-worker.js', mimetype='application/javascript')

# ============================================================
# RUN APP
# ============================================================
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
