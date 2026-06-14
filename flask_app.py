import os, sqlite3, re, random, string, math
from datetime import date, timedelta, datetime
from collections import defaultdict
from flask import Flask, render_template_string, request, redirect, url_for, session, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.secret_key = 'rockabyconnect-secret-key-change-in-production'
app.permanent_session_lifetime = timedelta(days=30)

# Initialize database on startup
with app.app_context():
    init_db()

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

SKILL_SUGGESTIONS = [
    'Plumbing', 'Electrical', 'Carpentry', 'Painting', 'Cleaning',
    'Tutoring', 'Graphic Design', 'Web Development', 'Tailoring',
    'Cooking', 'Driving', 'Bricklaying', 'Construction', 'Boda Rider',
    'Maid', 'Gardening', 'Security Guard', 'Welding', 'Salon/Hair dressing',
    'Farming', 'Other'
]

FREELANCER_STATUSES = ['Available', 'Occupied', 'On Leave']
VENDOR_STATUSES = ['Open', 'Closed', 'Away']

# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------
def init_db():
    conn = sqlite3.connect('rockabyconnect.db')
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.row_factory = sqlite3.Row
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
    c.execute("PRAGMA table_info(providers)")
    prov_cols = [col[1] for col in c.fetchall()]
    for col in ['skills', 'village', 'featured_expiry']:
        if col not in prov_cols:
            c.execute(f"ALTER TABLE providers ADD COLUMN {col} TEXT")

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
    c.execute("PRAGMA table_info(vendors)")
    vend_cols = [col[1] for col in c.fetchall()]
    for col in ['landmark', 'vendor_image2', 'vendor_image3', 'featured_expiry']:
        if col not in vend_cols:
            c.execute(f"ALTER TABLE vendors ADD COLUMN {col} TEXT")

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
    c.execute("PRAGMA table_info(jobs)")
    job_cols = [col[1] for col in c.fetchall()]
    for col in ['village', 'job_image', 'featured', 'featured_expiry']:
        if col not in job_cols:
            c.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT")

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

    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    # Insert admin if not exists
    c.execute("SELECT COUNT(*) FROM users WHERE id=1")
    if c.fetchone()[0] == 0:
        hashed = generate_password_hash('admin123')
        c.execute("INSERT INTO users (phone, name, password_hash) VALUES ('256751318876', 'RockabyTech Admin', ?)", (hashed,))

    conn.commit()
    conn.close()

# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect('rockabyconnect.db')
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA busy_timeout = 5000;")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None: db.close()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def generate_voucher_code():
    return 'WIFI-'+''.join(random.choices(string.ascii_uppercase+string.digits,k=4))+'-'+''.join(random.choices(string.ascii_uppercase+string.digits,k=4))+'-'+''.join(random.choices(string.ascii_uppercase+string.digits,k=4))

def whatsapp_link(phone):
    digits = ''.join(filter(str.isdigit, phone))
    if digits.startswith('0'): digits = '256' + digits[1:]
    elif not digits.startswith('256'): digits = '256' + digits
    return f"https://wa.me/{digits}"

def allowed_file(fn): return '.' in fn and fn.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def is_featured_now(featured_flag, expiry_date):
    if not featured_flag: return False
    if expiry_date is None: return True
    return date.today() <= date.fromisoformat(expiry_date)

def get_provider_count():
    db = get_db()
    return db.execute("SELECT COUNT(*) as c FROM providers").fetchone()['c']

def get_open_jobs_count():
    db = get_db()
    return db.execute("SELECT COUNT(*) as c FROM jobs WHERE status='Open'").fetchone()['c']

base_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RockabyConnect – {title}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        :root {
            --primary: #f5af19; --primary-dark: #e09e15; --secondary: #1a73e8;
            --bg: #f0f4f8; --card-bg: rgba(255,255,255,0.9); --glass-border: rgba(255,255,255,0.3);
            --text: #1a1a1a; --text-secondary: #666; --border: #e0e0e0;
            --radius: 16px; --shadow: 0 8px 32px rgba(0,0,0,0.08);
        }
        .dark-mode {
            --bg: #0f172a; --card-bg: rgba(30,41,59,0.9); --glass-border: rgba(255,255,255,0.08);
            --text: #f1f5f9; --text-secondary: #94a3b8; --border: #334155;
            --shadow: 0 8px 32px rgba(0,0,0,0.3);
        }
        * { margin:0; padding:0; box-sizing:border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            background-image: radial-gradient(circle at 10% 20%, rgba(245,175,25,0.05) 0%, transparent 50%),
                              radial-gradient(circle at 90% 80%, rgba(26,115,232,0.05) 0%, transparent 50%);
            color: var(--text); min-height:100vh;
        }
        .navbar {
            background: var(--card-bg); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            border-bottom:1px solid var(--glass-border); padding:14px 24px;
            position: sticky; top:0; z-index:1000; display:flex; align-items:center; justify-content:space-between;
        }
        .navbar .logo { font-size:1.3rem; font-weight:800; color:var(--primary); text-decoration:none; display:flex; align-items:center; gap:8px; }
        .nav-links { display:flex; gap:20px; align-items:center; }
        .nav-links a { color:var(--text-secondary); text-decoration:none; font-weight:500; transition:color 0.2s; }
        .nav-links a:hover { color:var(--primary); }
        .theme-toggle { background:none; border:none; color:var(--text); font-size:1.3rem; cursor:pointer; }
        .hamburger { display:none; font-size:1.5rem; cursor:pointer; background:none; border:none; color:var(--text); }
        .container { max-width:1000px; margin:24px auto; padding:0 20px; }
        .card {
            background: var(--card-bg); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            border-radius:var(--radius); padding:28px; margin-bottom:20px;
            box-shadow:var(--shadow); border:1px solid var(--glass-border);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .card:hover { transform: translateY(-2px); box-shadow: 0 12px 40px rgba(0,0,0,0.12); }
        .card-header { font-size:1.2rem; font-weight:700; margin-bottom:20px; border-bottom:1px solid var(--border); padding-bottom:14px; display:flex; justify-content:space-between; align-items:center; }
        .btn {
            display:inline-block; padding:10px 22px; background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color:#fff; border:none; border-radius:8px; font-weight:600; cursor:pointer; text-decoration:none; font-size:0.9rem; transition:all 0.2s; box-shadow:0 4px 15px rgba(245,175,25,0.3);
        }
        .btn:hover { transform: translateY(-1px); box-shadow:0 6px 20px rgba(245,175,25,0.4); }
        .btn-outline { background:transparent; border:2px solid var(--primary); color:var(--primary); box-shadow:none; }
        .btn-small { padding:5px 10px; font-size:0.8rem; }
        .btn-danger { background: linear-gradient(135deg, #dc3545, #ff6b6b); }
        .btn-success { background: linear-gradient(135deg, #28a745, #51cf66); }
        .btn-whatsapp { background: linear-gradient(135deg, #25D366, #128C7E); }
        .stat-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(180px, 1fr)); gap:15px; margin-bottom:20px; }
        .stat-card {
            background: var(--card-bg); border-radius:var(--radius); padding:24px; text-align:center;
            box-shadow:var(--shadow); border:1px solid var(--glass-border); position:relative; overflow:hidden;
        }
        .stat-card::before { content:''; position:absolute; top:-20px; right:-20px; width:60px; height:60px; background: linear-gradient(135deg, var(--primary), #6366f1); opacity:0.1; border-radius:50%; }
        .stat-card h3 { font-size:2rem; font-weight:800; color:var(--primary); position:relative; }
        .stat-card small { color:var(--text-secondary); font-size:0.85rem; position:relative; }
        .whatsapp-float {
            position:fixed; bottom:24px; right:24px; background: linear-gradient(135deg, #25D366, #128C7E);
            color:white; width:60px; height:60px; border-radius:50%; display:flex; align-items:center;
            justify-content:center; font-size:28px; box-shadow:0 8px 25px rgba(37,211,102,0.4);
            z-index:999; text-decoration:none; transition:transform 0.2s;
        }
        .whatsapp-float:hover { transform: scale(1.1); }
        label { display:block; margin-top:15px; font-weight:500; }
        input, textarea, select { width:100%; padding:10px 12px; margin-top:5px; border-radius:8px; border:1px solid var(--border); font-size:0.95rem; background:var(--card-bg); color:var(--text); }
        .badge { display:inline-block; padding:2px 8px; border-radius:4px; font-size:0.75rem; margin-left:8px; vertical-align:middle; color:white; }
        .badge-available { background:#28a745; } .badge-occupied { background:#ffc107; color:#333; } .badge-leave { background:#6c757d; }
        .badge-open { background:#17a2b8; } .badge-taken { background:#6f42c1; } .badge-closed { background:#dc3545; }
        .profile-pic { width:80px; height:80px; border-radius:50%; object-fit:cover; border:2px solid var(--primary); }
        .provider-card, .job-card, .vendor-card { display:flex; align-items:center; gap:15px; padding:15px 0; border-bottom:1px solid var(--border); }
        .provider-card:last-child, .job-card:last-child, .vendor-card:last-child { border-bottom:none; }
        .provider-info, .job-info, .vendor-info { flex:1; }
        .search-bar input { width:100%; padding:12px 15px; border-radius:30px; border:1px solid var(--border); margin-bottom:20px; background:var(--card-bg); color:var(--text); }
        .review-card { border-left:3px solid var(--primary); padding:10px; margin:10px 0; background:rgba(245,175,25,0.05); border-radius:0 8px 8px 0; }
        .rating { color:var(--primary); font-size:1.2rem; }
        footer { text-align:center; padding:24px; color:var(--text-secondary); }
        table { width:100%; border-collapse:collapse; }
        th, td { padding:10px; text-align:left; border-bottom:1px solid var(--border); }
        .alert { padding:12px 18px; border-radius:8px; margin-bottom:15px; }
        .alert-success { background:rgba(40,167,69,0.15); color:#155724; border:1px solid rgba(40,167,69,0.3); }
        .alert-error { background:rgba(220,53,69,0.15); color:#721c24; border:1px solid rgba(220,53,69,0.3); }
        @media (max-width:768px) {
            .nav-links { display:none; }
            .hamburger { display:block; }
            .nav-links.open { display:flex; flex-direction:column; position:absolute; top:60px; left:0; right:0; background:var(--card-bg); padding:20px; border-bottom:1px solid var(--border); }
        }
    </style>
</head>
<body>
    <nav class="navbar">
        <a href="/" class="logo">🔗 ROCKABY<span style="color:var(--primary);">CONNECT</span></a>
        <button class="hamburger" onclick="toggleMenu()">&#9776;</button>
        <div class="nav-links" id="navMenu">
            <a href="/">Home</a>
            <a href="/list">Find Skills</a>
            <a href="/jobs">Jobs</a>
            <a href="/vendors">Vendors</a>
            {% if session.user_id %}
                <a href="/dashboard">Dashboard</a>
                <a href="/logout">Logout</a>
            {% else %}
                <a href="/login">Login</a>
                <a href="/signup">Sign Up</a>
            {% endif %}
            <button class="theme-toggle" onclick="toggleTheme()" title="Toggle theme">🌓</button>
        </div>
    </nav>
    <div class="container">{content}</div>
    <a href="https://wa.me/256751318876?text=Hi%20RockabyConnect%20Support" target="_blank" class="whatsapp-float">💬</a>
    <footer>&copy; 2025 RockabyTech – Connecting Skills, Building Uganda</footer>
    <script>
        function toggleMenu() { document.getElementById('navMenu').classList.toggle('open'); }
        function toggleTheme() { document.body.classList.toggle('dark-mode'); localStorage.setItem('theme', document.body.classList.contains('dark-mode') ? 'dark' : 'light'); }
        if (localStorage.getItem('theme') === 'dark') { document.body.classList.add('dark-mode'); }
    </script>
</body>
</html>
"""

def render_page(title, content):
    page = base_template.replace('{title}', title).replace('{content}', content)
    return page

# ============================================================
# HOME PAGE
# ============================================================
@app.route('/')
def index():
    db = get_db()
    featured_providers = db.execute("""
        SELECT p.*, u.name, u.phone FROM providers p
        JOIN users u ON p.user_id = u.id
        WHERE p.featured = 1 AND (p.featured_expiry IS NULL OR p.featured_expiry >= date('now'))
        ORDER BY p.id DESC LIMIT 4
    """).fetchall()
    featured_jobs = db.execute("""
        SELECT j.*, u.name as employer_name FROM jobs j
        JOIN users u ON j.employer_id = u.id
        WHERE j.status='Open' AND j.featured = 1 AND (j.featured_expiry IS NULL OR j.featured_expiry >= date('now'))
        ORDER BY j.id DESC LIMIT 4
    """).fetchall()
    content = f'''
    <div class="card" style="text-align:center; background: linear-gradient(135deg, rgba(245,175,25,0.2), rgba(26,115,232,0.2));">
        <h1>🔗 Find Work & Hire Talent</h1>
        <p style="margin:15px 0;">Uganda's freelance marketplace connecting skilled workers with local jobs</p>
        <div style="display:flex; gap:10px; justify-content:center; flex-wrap:wrap;">
            <a href="/list" class="btn">🔍 Find Freelancers</a>
            <a href="/jobs" class="btn btn-outline">💼 Browse Jobs</a>
            <a href="/vendors" class="btn btn-outline">🏪 Local Vendors</a>
        </div>
    </div>
    <div class="stat-grid">
        <div class="stat-card"><h3>{get_provider_count()}</h3><small>Available Freelancers</small></div>
        <div class="stat-card"><h3>{get_open_jobs_count()}</h3><small>Open Jobs</small></div>
        <div class="stat-card"><h3>10K+</h3><small>Monthly Visitors</small></div>
    </div>
    '''
    if featured_providers:
        content += '<div class="card"><div class="card-header">⭐ Featured Freelancers</div>'
        for p in featured_providers:
            content += f'''
            <div class="provider-card">
                <img src="{p['profile_pic'] or '/static/default-avatar.png'}" class="profile-pic" onerror="this.src='/static/default-avatar.png'">
                <div class="provider-info"><strong>{p['name']}</strong><br>{p['skills'] or 'No skills listed'}<br>
                <span class="badge badge-{'available' if p['status']=='Available' else 'occupied' if p['status']=='Occupied' else 'leave'}">{p['status']}</span></div>
                <a href="/provider/{p['id']}" class="btn btn-small">View →</a>
            </div>'''
        content += '</div>'
    if featured_jobs:
        content += '<div class="card"><div class="card-header">🔥 Featured Jobs</div>'
        for j in featured_jobs:
            content += f'''
            <div class="job-card">
                <div class="job-info"><strong>{j['title']}</strong><br>{j['company'] or 'Individual Employer'} • {j['location'] or 'Uganda'}<br>
                <span class="badge badge-open">Open</span></div>
                <a href="/job/{j['id']}" class="btn btn-small">Apply →</a>
            </div>'''
        content += '</div>'
    return render_page('Home', content)

# ============================================================
# AUTHENTICATION
# ============================================================
@app.route('/signup', methods=['GET','POST'])
def signup():
    error = None
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        name = request.form['name'].strip()
        pwd = request.form['password']
        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()
        if existing:
            error = "Phone number already registered"
        else:
            hashed = generate_password_hash(pwd)
            db.execute("INSERT INTO users (phone, name, password_hash) VALUES (?,?,?)", (phone, name, hashed))
            db.commit()
            user = db.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()
            session['user_id'] = user['id']
            session.permanent = True
            return redirect(url_for('choose_role'))
    content = f'''
    <div class="card" style="max-width:450px; margin:0 auto;">
        <div class="card-header">📝 Create Account</div>
        {"<div class='alert alert-error'>"+error+"</div>" if error else ""}
        <form method="post">
            <label>📞 Phone (e.g., 0751318876)</label>
            <input type="tel" name="phone" required>
            <label>👤 Full Name</label>
            <input type="text" name="name" required>
            <label>🔒 Password</label>
            <input type="password" name="password" required>
            <button type="submit" class="btn" style="width:100%; margin-top:20px;">Sign Up →</button>
        </form>
        <p style="margin-top:20px; text-align:center;">Already have an account? <a href="/login">Login</a></p>
    </div>'''
    return render_page('Sign Up', content)

@app.route('/login', methods=['GET','POST'])
def login():
    error = None
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        pwd = request.form['password']
        db = get_db()
        user = db.execute("SELECT id, password_hash FROM users WHERE phone=?", (phone,)).fetchone()
        if user and check_password_hash(user['password_hash'], pwd):
            session['user_id'] = user['id']
            session.permanent = True
            return redirect(url_for('dashboard'))
        error = "Invalid phone or password"
    content = f'''
    <div class="card" style="max-width:450px; margin:0 auto;">
        <div class="card-header">🔐 Login</div>
        {"<div class='alert alert-error'>"+error+"</div>" if error else ""}
        <form method="post">
            <label>📞 Phone</label>
            <input type="tel" name="phone" required>
            <label>🔒 Password</label>
            <input type="password" name="password" required>
            <button type="submit" class="btn" style="width:100%; margin-top:20px;">Login →</button>
        </form>
        <p style="margin-top:20px; text-align:center;">New user? <a href="/signup">Create account</a></p>
    </div>'''
    return render_page('Login', content)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/choose-role', methods=['GET','POST'])
@login_required
def choose_role():
    db = get_db()
    existing = db.execute("SELECT id FROM providers WHERE user_id=?", (session['user_id'],)).fetchone()
    existing_vendor = db.execute("SELECT id FROM vendors WHERE user_id=?", (session['user_id'],)).fetchone()
    if existing or existing_vendor:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        role = request.form['role']
        if role == 'freelancer':
            db.execute("INSERT INTO providers (user_id, status) VALUES (?, 'Available')", (session['user_id'],))
            db.commit()
        else:
            db.execute("INSERT INTO vendors (user_id, business_name, status) VALUES (?, 'Pending Setup', 'Open')", (session['user_id'],))
            db.commit()
        return redirect(url_for('dashboard'))
    content = '''
    <div class="card" style="text-align:center;">
        <div class="card-header">👋 Welcome! Choose Your Role</div>
        <div style="display:flex; gap:20px; justify-content:center; flex-wrap:wrap;">
            <form method="post" style="display:inline;"><input type="hidden" name="role" value="freelancer"><button type="submit" class="btn">🔧 I'm a Freelancer</button></form>
            <form method="post" style="display:inline;"><input type="hidden" name="role" value="vendor"><button type="submit" class="btn btn-outline">🏪 I'm a Vendor</button></form>
        </div>
    </div>'''
    return render_page('Choose Role', content)

# ============================================================
# FREELANCERS (Providers)
# ============================================================
@app.route('/list')
def list_providers():
    search = request.args.get('search', '')
    db = get_db()
    query = "SELECT p.*, u.name, u.phone FROM providers p JOIN users u ON p.user_id = u.id WHERE 1=1"
    params = []
    if search:
        query += " AND (u.name LIKE ? OR p.skills LIKE ? OR p.district LIKE ?)"
        params = [f'%{search}%', f'%{search}%', f'%{search}%']
    query += " ORDER BY p.featured DESC, p.id DESC"
    providers = db.execute(query, params).fetchall()
    content = f'''
    <div class="card"><div class="card-header">🔍 Find Freelancers</div>
    <form method="get"><div class="search-bar"><input type="text" name="search" placeholder="Search by name, skill, or district..." value="{search}"></div></form>
    <div id="providers-list">'''
    for p in providers:
        featured_badge = '⭐ ' if is_featured_now(p['featured'], p['featured_expiry']) else ''
        content += f'''
        <div class="provider-card">
            <img src="{p['profile_pic'] or '/static/default-avatar.png'}" class="profile-pic" onerror="this.src='/static/default-avatar.png'">
            <div class="provider-info"><strong>{featured_badge}{p['name']}</strong><br>{p['skills'] or 'No skills listed'} • {p['district'] or 'No district'}<br>
            <span class="badge badge-{'available' if p['status']=='Available' else 'occupied' if p['status']=='Occupied' else 'leave'}">{p['status']}</span></div>
            <a href="/provider/{p['id']}" class="btn btn-small">View →</a>
        </div>'''
    content += '</div></div>'
    return render_page('Find Freelancers', content)

@app.route('/provider/<int:pid>')
def provider_detail(pid):
    db = get_db()
    p = db.execute("SELECT p.*, u.name, u.phone FROM providers p JOIN users u ON p.user_id = u.id WHERE p.id=?", (pid,)).fetchone()
    if not p: return "Provider not found", 404
    reviews = db.execute("SELECT r.*, u.name FROM reviews r JOIN users u ON r.reviewer_id=u.id WHERE r.provider_id=? ORDER BY r.created_at DESC", (pid,)).fetchall()
    avg_rating = db.execute("SELECT AVG(rating) as avg FROM reviews WHERE provider_id=?", (pid,)).fetchone()['avg'] or 0
    whatsapp = whatsapp_link(p['phone'])
    content = f'''
    <div class="card">
        <div class="provider-card" style="padding:0; flex-wrap:wrap;">
            <img src="{p['profile_pic'] or '/static/default-avatar.png'}" style="width:100px; height:100px;" class="profile-pic">
            <div class="provider-info"><h2>{p['name']}</h2>
            <div class="rating">{"⭐"*int(round(avg_rating))}{"☆"*(5-int(round(avg_rating)))} ({len(reviews)} reviews)</div>
            <p><strong>Skills:</strong> {p['skills'] or 'Not specified'}</p>
            <p><strong>Location:</strong> {p['district'] or 'N/A'} {p['village'] or ''}</p>
            <p><strong>Status:</strong> <span class="badge badge-{'available' if p['status']=='Available' else 'occupied' if p['status']=='Occupied' else 'leave'}">{p['status']}</span></p>
            <p><strong>Bio:</strong> {p['bio'] or 'No bio yet'}</p>
            <a href="{whatsapp}" target="_blank" class="btn btn-whatsapp">💬 Contact on WhatsApp</a>
            </div>
        </div>
    </div>
    <div class="card"><div class="card-header">📝 Reviews</div>'''
    for r in reviews:
        content += f'<div class="review-card">{"⭐"*r["rating"]} <strong>{r["name"]}</strong> - {r["comment"] or "No comment"}<br><small>{r["created_at"]}</small></div>'
    if session.get('user_id'):
        existing = db.execute("SELECT id FROM reviews WHERE provider_id=? AND reviewer_id=?", (pid, session['user_id'])).fetchone()
        if not existing:
            content += '''
            <form method="post" action="/review/'''+str(pid)+'''" style="margin-top:15px;">
                <select name="rating" required><option value="">Rating</option>'''+''.join([f'<option value="{i}">{"⭐"*i}</option>' for i in range(1,6)])+'''</select>
                <textarea name="comment" placeholder="Write a review..."></textarea>
                <button type="submit" class="btn btn-small">Submit Review</button>
            </form>'''
    content += '</div>'
    return render_page(p['name'], content)

@app.route('/review/<int:pid>', methods=['POST'])
@login_required
def submit_review(pid):
    rating = int(request.form['rating'])
    comment = request.form.get('comment', '')
    db = get_db()
    db.execute("INSERT INTO reviews (provider_id, reviewer_id, rating, comment) VALUES (?,?,?,?)",
               (pid, session['user_id'], rating, comment))
    db.commit()
    return redirect(url_for('provider_detail', pid=pid))

# ============================================================
# JOBS
# ============================================================
@app.route('/jobs')
def list_jobs():
    search = request.args.get('search', '')
    db = get_db()
    query = "SELECT j.*, u.name as employer_name FROM jobs j JOIN users u ON j.employer_id=u.id WHERE j.status='Open'"
    params = []
    if search:
        query += " AND (j.title LIKE ? OR j.description LIKE ? OR j.location LIKE ? OR j.village LIKE ?)"
        params = [f'%{search}%'] * 4
    query += " ORDER BY j.featured DESC, j.id DESC"
    jobs = db.execute(query, params).fetchall()
    content = f'''
    <div class="card"><div class="card-header">💼 Job Board</div>
    <form method="get"><div class="search-bar"><input type="text" name="search" placeholder="Search jobs..." value="{search}"></div></form>
    <div id="jobs-list">'''
    for j in jobs:
        featured_badge = '🔥 ' if is_featured_now(j['featured'], j['featured_expiry']) else ''
        content += f'''
        <div class="job-card">
            <div class="job-info"><strong>{featured_badge}{j['title']}</strong><br>{j['company'] or 'Employer'} • {j['location'] or 'Uganda'}<br>
            <span class="badge badge-open">Open</span> <small>{j['posted_date']}</small></div>
            <a href="/job/{j['id']}" class="btn btn-small">View →</a>
        </div>'''
    content += '</div></div>'
    return render_page('Jobs', content)

@app.route('/job/<int:jid>')
def job_detail(jid):
    db = get_db()
    j = db.execute("SELECT j.*, u.name, u.phone FROM jobs j JOIN users u ON j.employer_id=u.id WHERE j.id=?", (jid,)).fetchone()
    if not j: return "Job not found", 404
    whatsapp = whatsapp_link(j['phone'])
    content = f'''
    <div class="card">
        <h2>{j['title']}</h2>
        <p><strong>Employer:</strong> {j['employer_name']}</p>
        <p><strong>Company:</strong> {j['company'] or 'Individual'}</p>
        <p><strong>Location:</strong> {j['location'] or 'N/A'} {j['village'] or ''}</p>
        <p><strong>Status:</strong> <span class="badge badge-{'open' if j['status']=='Open' else 'taken'}">{j['status']}</span></p>
        <p><strong>Description:</strong> {j['description'] or 'No description'}</p>
        <a href="{whatsapp}" target="_blank" class="btn btn-whatsapp">📱 Apply via WhatsApp</a>
    </div>'''
    return render_page(j['title'], content)

@app.route('/post-job', methods=['GET','POST'])
@login_required
def post_job():
    if request.method == 'POST':
        title = request.form['title']
        company = request.form.get('company', '')
        description = request.form['description']
        location = request.form.get('location', '')
        village = request.form.get('village', '')
        contact = request.form.get('contact', '')
        db = get_db()
        db.execute("INSERT INTO jobs (employer_id, title, company, description, location, village, contact, status) VALUES (?,?,?,?,?,?,?,'Open')",
                   (session['user_id'], title, company, description, location, village, contact))
        db.commit()
        return redirect(url_for('list_jobs'))
    content = '''
    <div class="card"><div class="card-header">📢 Post a Job</div>
    <form method="post">
        <label>Job Title *</label><input type="text" name="title" required>
        <label>Company Name (optional)</label><input type="text" name="company">
        <label>Description *</label><textarea name="description" rows="4" required></textarea>
        <label>Location (District)</label><input type="text" name="location">
        <label>Village/Town</label><input type="text" name="village">
        <label>Contact Info (for applicants)</label><input type="text" name="contact">
        <button type="submit" class="btn" style="margin-top:20px;">Post Job →</button>
    </form></div>'''
    return render_page('Post Job', content)

# ============================================================
# VENDORS
# ============================================================
@app.route('/vendors')
def list_vendors():
    search = request.args.get('search', '')
    db = get_db()
    query = "SELECT v.*, u.name, u.phone FROM vendors v JOIN users u ON v.user_id=u.id WHERE v.status='Open'"
    params = []
    if search:
        query += " AND (v.business_name LIKE ? OR v.district LIKE ? OR v.village LIKE ?)"
        params = [f'%{search}%', f'%{search}%', f'%{search}%']
    query += " ORDER BY v.featured DESC, v.id DESC"
    vendors = db.execute(query, params).fetchall()
    content = f'''
    <div class="card"><div class="card-header">🏪 Local Vendors</div>
    <form method="get"><div class="search-bar"><input type="text" name="search" placeholder="Search businesses..." value="{search}"></div></form>
    <div id="vendors-list">'''
    for v in vendors:
        featured_badge = '⭐ ' if is_featured_now(v['featured'], v['featured_expiry']) else ''
        content += f'''
        <div class="vendor-card">
            <div class="vendor-info"><strong>{featured_badge}{v['business_name']}</strong><br>{v['district'] or 'N/A'} • {v['village'] or ''}<br>
            <span class="badge badge-open">{v['status']}</span></div>
            <a href="/vendor/{v['id']}" class="btn btn-small">View →</a>
        </div>'''
    content += '</div></div>'
    return render_page('Vendors', content)

@app.route('/vendor/<int:vid>')
def vendor_detail(vid):
    db = get_db()
    v = db.execute("SELECT v.*, u.name, u.phone FROM vendors v JOIN users u ON v.user_id=u.id WHERE v.id=?", (vid,)).fetchone()
    if not v: return "Vendor not found", 404
    whatsapp = whatsapp_link(v['phone'])
    content = f'''
    <div class="card">
        <h2>{v['business_name']}</h2>
        <p><strong>Owner:</strong> {v['name']}</p>
        <p><strong>Location:</strong> {v['district'] or 'N/A'} {v['village'] or ''} {v['landmark'] or ''}</p>
        <p><strong>Status:</strong> <span class="badge badge-{'open' if v['status']=='Open' else 'closed'}">{v['status']}</span></p>
        <p><strong>About:</strong> {v['bio'] or 'No description'}</p>
        <a href="{whatsapp}" target="_blank" class="btn btn-whatsapp">📞 Contact Vendor</a>
    </div>'''
    return render_page(v['business_name'], content)

# ============================================================
# DASHBOARD & PROFILE MANAGEMENT
# ============================================================
@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    provider = db.execute("SELECT * FROM providers WHERE user_id=?", (session['user_id'],)).fetchone()
    vendor = db.execute("SELECT * FROM vendors WHERE user_id=?", (session['user_id'],)).fetchone()
    is_admin = db.execute("SELECT phone FROM users WHERE id=?", (session['user_id'],)).fetchone()['phone'] == '256751318876'
    
    content = '<div class="card"><div class="card-header">📊 Dashboard</div>'
    if provider:
        content += f'''
        <div style="margin-bottom:15px;">
            <h3>🔧 Freelancer Profile</h3>
            <p>Status: <span class="badge badge-{'available' if provider['status']=='Available' else 'occupied'}">{provider['status']}</span></p>
            <p>Featured: {'✅ Active' if is_featured_now(provider['featured'], provider['featured_expiry']) else '❌ Not featured'}</p>
            <a href="/edit-profile" class="btn btn-small">✏️ Edit Profile</a>
            <a href="/boost-profile" class="btn btn-small btn-outline">🚀 Boost (Get Featured)</a>
        </div>'''
    if vendor:
        content += f'''
        <div style="margin-bottom:15px;">
            <h3>🏪 Vendor Profile</h3>
            <p>Business: {vendor['business_name']}</p>
            <p>Status: <span class="badge badge-open">{vendor['status']}</span></p>
            <a href="/edit-vendor" class="btn btn-small">✏️ Edit Vendor</a>
            <a href="/boost-vendor" class="btn btn-small btn-outline">🚀 Boost Vendor</a>
        </div>'''
    my_jobs = db.execute("SELECT * FROM jobs WHERE employer_id=?", (session['user_id'],)).fetchall()
    if my_jobs:
        content += '<div class="card-header">📋 My Job Posts</div>'
        for j in my_jobs:
            content += f'<div class="job-card"><div>{j["title"]} - <span class="badge badge-{"open" if j["status"]=="Open" else "taken"}">{j["status"]}</span></div><a href="/job/{j["id"]}" class="btn btn-small">View</a></div>'
    if is_admin:
        boost_requests = db.execute("SELECT b.*, u.name, u.phone FROM boost_requests b JOIN users u ON b.user_id=u.id WHERE b.status='pending' ORDER BY b.request_date DESC").fetchall()
        if boost_requests:
            content += '<div class="card-header">👑 Admin - Boost Requests</div><table><tr><th>User</th><th>Plan</th><th>Type</th><th>Action</th></tr>'
            for br in boost_requests:
                content += f'<tr><td>{br["name"]}</td><td>{br["plan"]}</td><td>{br["boost_type"]}</td><td><a href="/approve-boost/{br["id"]}" class="btn btn-small btn-success">Approve</a></td></tr>'
            content += '</table>'
    content += '</div>'
    return render_page('Dashboard', content)

@app.route('/edit-profile', methods=['GET','POST'])
@login_required
def edit_profile():
    db = get_db()
    provider = db.execute("SELECT * FROM providers WHERE user_id=?", (session['user_id'],)).fetchone()
    if not provider:
        return redirect(url_for('choose_role'))
    if request.method == 'POST':
        skills = request.form.get('skills', '')
        district = request.form.get('district', '')
        village = request.form.get('village', '')
        bio = request.form.get('bio', '')
        status = request.form.get('status', 'Available')
        db.execute("UPDATE providers SET skills=?, district=?, village=?, bio=?, status=? WHERE user_id=?", 
                   (skills, district, village, bio, status, session['user_id']))
        db.commit()
        return redirect(url_for('dashboard'))
    content = f'''
    <div class="card"><div class="card-header">✏️ Edit Freelancer Profile</div>
    <form method="post">
        <label>Skills (comma separated)</label><input type="text" name="skills" value="{provider['skills'] or ''}" placeholder="Plumbing, Electrical, Carpentry...">
        <label>District</label><input type="text" name="district" value="{provider['district'] or ''}">
        <label>Village/Town</label><input type="text" name="village" value="{provider['village'] or ''}">
        <label>Bio</label><textarea name="bio" rows="3">{provider['bio'] or ''}</textarea>
        <label>Availability Status</label><select name="status"><option {"selected" if provider['status']=='Available' else ""}>Available</option><option {"selected" if provider['status']=='Occupied' else ""}>Occupied</option><option {"selected" if provider['status']=='On Leave' else ""}>On Leave</option></select>
        <button type="submit" class="btn" style="margin-top:20px;">Save Changes</button>
    </form></div>'''
    return render_page('Edit Profile', content)

@app.route('/boost-profile', methods=['GET','POST'])
@login_required
def boost_profile():
    if request.method == 'POST':
        plan = request.form['plan']
        transaction_id = request.form.get('transaction_id', '')
        db = get_db()
        db.execute("INSERT INTO boost_requests (user_id, transaction_id, plan, boost_type, status) VALUES (?,?,?,'profile','pending')",
                   (session['user_id'], transaction_id, plan))
        db.commit()
        return redirect(url_for('dashboard'))
    content = '''
    <div class="card"><div class="card-header">🚀 Boost Your Profile</div>
    <p>Get featured at the top of search results for 7 days!</p>
    <form method="post">
        <label>Select Plan</label>
        <select name="plan" required>
            <option value="1day">1 Day - 5,000 UGX</option>
            <option value="7days">7 Days - 25,000 UGX</option>
            <option value="30days">30 Days - 80,000 UGX</option>
        </select>
        <label>Transaction ID (MTN/Airtel Money)</label>
        <input type="text" name="transaction_id" placeholder="Enter your payment reference">
        <button type="submit" class="btn" style="margin-top:20px;">Submit Request →</button>
    </form>
    <p style="margin-top:15px; font-size:0.8rem;">Send payment to 0751318876 (MTN Momo) and enter the transaction ID above.</p>
    </div>'''
    return render_page('Boost Profile', content)

@app.route('/approve-boost/<int:bid>')
@login_required
def approve_boost(bid):
    db = get_db()
    user = db.execute("SELECT phone FROM users WHERE id=?", (session['user_id'],)).fetchone()
    if user['phone'] != '256751318876':
        return "Unauthorized", 403
    boost = db.execute("SELECT * FROM boost_requests WHERE id=?", (bid,)).fetchone()
    if not boost:
        return "Request not found", 404
    days = {'1day':1, '7days':7, '30days':30}.get(boost['plan'], 7)
    expiry = (date.today() + timedelta(days=days)).isoformat()
    if boost['boost_type'] == 'profile':
        db.execute("UPDATE providers SET featured=1, featured_expiry=? WHERE user_id=?", (expiry, boost['user_id']))
    else:
        db.execute("UPDATE vendors SET featured=1, featured_expiry=? WHERE user_id=?", (expiry, boost['user_id']))
    db.execute("UPDATE boost_requests SET status='approved' WHERE id=?", (bid,))
    db.commit()
    return redirect(url_for('dashboard'))

# ============================================================
# RUN APP
# ============================================================
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
