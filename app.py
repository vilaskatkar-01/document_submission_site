from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
import os
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-this'

# ========== EMAIL CONFIGURATION ==========
# For Gmail (replace with your credentials)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'  # CHANGE THIS
app.config['MAIL_PASSWORD'] = 'your-app-password'      # CHANGE THIS
app.config['MAIL_DEFAULT_SENDER'] = 'your-email@gmail.com'

mail = Mail(app)

# ========== UPLOAD CONFIGURATION ==========
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ========== LOGIN MANAGER ==========
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to access this page."

class User(UserMixin):
    def __init__(self, id, username, role, email=None):
        self.id = id
        self.username = username
        self.role = role
        self.email = email

# ========== DATABASE ==========
def init_db():
    conn = sqlite3.connect('submissions.db')
    c = conn.cursor()
    
    # Documents table
    c.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            upload_date TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            submitted_by TEXT,
            category TEXT DEFAULT 'General'
        )
    ''')
    
    # Users table (with email)
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'submitter',
            email TEXT
        )
    ''')
    
    # Check if admin exists
    c.execute('SELECT * FROM users WHERE username = "admin"')
    if not c.fetchone():
        hashed_pw = generate_password_hash('admin123')
        c.execute('INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)',
                  ('admin', hashed_pw, 'admin', 'admin@example.com'))
    
    conn.commit()
    conn.close()

init_db()

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('submissions.db')
    c = conn.cursor()
    c.execute('SELECT id, username, role, email FROM users WHERE id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    if user:
        return User(user[0], user[1], user[2], user[3])
    return None

# ========== EMAIL FUNCTIONS ==========
def send_email_notification(recipient_email, subject, body):
    """Send email notification"""
    try:
        msg = Message(subject, recipients=[recipient_email])
        msg.body = body
        mail.send(msg)
        return True
    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False

def get_user_email(username):
    """Get email of a user"""
    conn = sqlite3.connect('submissions.db')
    c = conn.cursor()
    c.execute('SELECT email FROM users WHERE username = ?', (username,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

# ========== ROUTES ==========
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form.get('email', '')
        role = request.form.get('role', 'submitter')
        
        hashed_pw = generate_password_hash(password)
        
        try:
            conn = sqlite3.connect('submissions.db')
            c = conn.cursor()
            c.execute('INSERT INTO users (username, password, role, email) VALUES (?, ?, ?, ?)',
                      (username, hashed_pw, role, email))
            conn.commit()
            conn.close()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists!', 'danger')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('submissions.db')
        c = conn.cursor()
        c.execute('SELECT id, username, password, role, email FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            user_obj = User(user[0], user[1], user[3], user[4])
            login_user(user_obj)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password!', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/submit', methods=['POST'])
@login_required
def submit():
    if 'document' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('index'))
    
    file = request.files['document']
    category = request.form.get('category', 'General')
    
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('index'))
    
    if file:
        filename = file.filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Save to database
        conn = sqlite3.connect('submissions.db')
        c = conn.cursor()
        c.execute(
            'INSERT INTO documents (filename, filepath, upload_date, submitted_by, category) VALUES (?, ?, ?, ?, ?)',
            (filename, filepath, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), current_user.username, category)
        )
        conn.commit()
        conn.close()
        
        # ===== SEND EMAIL NOTIFICATION =====
        # Email to submitter
        user_email = get_user_email(current_user.username)
        if user_email:
            subject = f"📄 Document Submitted: {filename}"
            body = f"""Hello {current_user.username},

Your document '{filename}' has been successfully submitted.

📋 Details:
- Document: {filename}
- Category: {category}
- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Status: Pending

You can track your document status in the dashboard.

Thank you!"""
            send_email_notification(user_email, subject, body)
        
        # Email to admin (optional - uncomment if you want)
        # admin_email = get_user_email('admin')
        # if admin_email:
        #     subject = f"📄 New Document Submission: {filename}"
        #     body = f"""A new document has been submitted by {current_user.username}.

        # 📋 Details:
        # - Document: {filename}
        # - Category: {category}
        # - Submitted by: {current_user.username}
        # - Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

        # Please review it in the admin dashboard.
        # """
        #     send_email_notification(admin_email, subject, body)
        
        flash(f"✅ Document '{filename}' submitted successfully! Check your email for confirmation.", 'success')
        return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = sqlite3.connect('submissions.db')
    c = conn.cursor()
    
    if current_user.role == 'admin':
        c.execute('SELECT id, filename, upload_date, status, submitted_by, category FROM documents ORDER BY id DESC')
    else:
        c.execute('SELECT id, filename, upload_date, status, submitted_by, category FROM documents WHERE submitted_by = ? ORDER BY id DESC',
                  (current_user.username,))
    
    documents = c.fetchall()
    conn.close()
    return render_template('dashboard.html', documents=documents, user_role=current_user.role)

@app.route('/update_status/<int:doc_id>/<status>')
@login_required
def update_status(doc_id, status):
    if current_user.role != 'admin':
        flash('Only admins can update status!', 'danger')
        return redirect(url_for('dashboard'))
    
    conn = sqlite3.connect('submissions.db')
    c = conn.cursor()
    
    # Get document info for email
    c.execute('SELECT filename, submitted_by FROM documents WHERE id = ?', (doc_id,))
    doc = c.fetchone()
    
    if doc:
        filename, submitted_by = doc
        c.execute('UPDATE documents SET status = ? WHERE id = ?', (status, doc_id))
        conn.commit()
        
        # ===== SEND EMAIL NOTIFICATION =====
        user_email = get_user_email(submitted_by)
        if user_email:
            if status == 'Approved':
                subject = f"✅ Document Approved: {filename}"
                body = f"""Hello {submitted_by},

Great news! Your document '{filename}' has been APPROVED.

📋 Document Details:
- Document: {filename}
- Status: Approved ✅
- Reviewed by: {current_user.username}
- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Your document has been verified and accepted. Thank you for your submission!

Best regards,
Document Management Team"""
            else:
                subject = f"❌ Document Rejected: {filename}"
                body = f"""Hello {submitted_by},

We regret to inform you that your document '{filename}' has been REJECTED.

📋 Document Details:
- Document: {filename}
- Status: Rejected ❌
- Reviewed by: {current_user.username}
- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Please check your document and resubmit if needed. If you have any questions, please contact the admin.

Best regards,
Document Management Team"""
            
            send_email_notification(user_email, subject, body)
        
        flash(f'Status updated to {status} and email sent to {submitted_by}!', 'success')
    
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/delete/<int:doc_id>')
@login_required
def delete_document(doc_id):
    conn = sqlite3.connect('submissions.db')
    c = conn.cursor()
    
    if current_user.role != 'admin':
        c.execute('SELECT submitted_by FROM documents WHERE id = ?', (doc_id,))
        result = c.fetchone()
        if result and result[0] != current_user.username:
            flash('You can only delete your own documents!', 'danger')
            conn.close()
            return redirect(url_for('dashboard'))
    
    c.execute('SELECT filepath, filename, submitted_by FROM documents WHERE id = ?', (doc_id,))
    result = c.fetchone()
    
    if result:
        filepath, filename, submitted_by = result
        if os.path.exists(filepath):
            os.remove(filepath)
        c.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
        conn.commit()
        
        # ===== SEND EMAIL NOTIFICATION =====
        user_email = get_user_email(submitted_by)
        if user_email and current_user.role == 'admin':
            subject = f"🗑️ Document Deleted: {filename}"
            body = f"""Hello {submitted_by},

Your document '{filename}' has been DELETED by admin.

📋 Document Details:
- Document: {filename}
- Deleted by: {current_user.username}
- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

If you have any questions, please contact the admin.

Best regards,
Document Management Team"""
            send_email_notification(user_email, subject, body)
        
        flash('Document deleted successfully!', 'success')
    
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/admin/users')
@login_required
def manage_users():
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('dashboard'))
    
    conn = sqlite3.connect('submissions.db')
    c = conn.cursor()
    c.execute('SELECT id, username, role, email FROM users')
    users = c.fetchall()
    conn.close()
    return render_template('users.html', users=users)

@app.route('/admin/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        flash('Access denied!', 'danger')
        return redirect(url_for('dashboard'))
    
    if user_id == 1:
        flash('Cannot delete the main admin account!', 'danger')
        return redirect(url_for('manage_users'))
    
    conn = sqlite3.connect('submissions.db')
    c = conn.cursor()
    c.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    flash('User deleted successfully!', 'success')
    return redirect(url_for('manage_users'))

if __name__ == '__main__':
    app.run(debug=True)