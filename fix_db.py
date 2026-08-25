import sqlite3

conn = sqlite3.connect('submissions.db')
c = conn.cursor()

# Check if columns exist and add them if missing
try:
    c.execute('ALTER TABLE documents ADD COLUMN submitted_by TEXT')
    print("✅ Added 'submitted_by' column")
except sqlite3.OperationalError:
    print("ℹ️ 'submitted_by' column already exists")

try:
    c.execute('ALTER TABLE documents ADD COLUMN category TEXT DEFAULT "General"')
    print("✅ Added 'category' column")
except sqlite3.OperationalError:
    print("ℹ️ 'category' column already exists")

# Also check if users table exists
c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'submitter'
    )
''')
print("✅ Users table ready")

# Check if admin exists
c.execute('SELECT * FROM users WHERE username = "admin"')
if not c.fetchone():
    from werkzeug.security import generate_password_hash
    hashed_pw = generate_password_hash('admin123')
    c.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
              ('admin', hashed_pw, 'admin'))
    print("✅ Admin user created")

conn.commit()
conn.close()
print("🎉 Database fixed successfully!")