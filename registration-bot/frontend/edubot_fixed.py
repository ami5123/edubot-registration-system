import json
import boto3
import hashlib
import uuid
from datetime import datetime

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
users_table = dynamodb.Table('edubot-users')

def lambda_handler(event, context):
    # Handle OPTIONS requests for CORS
    if event['httpMethod'] == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            },
            'body': ''
        }
    
    # Handle GET requests - serve frontend
    if event['httpMethod'] == 'GET':
        return serve_html()
    
    # Handle POST requests - login/registration
    if event['httpMethod'] == 'POST':
        return handle_auth_request(event, context)
    
    # Handle other methods
    return {
        'statusCode': 404,
        'body': 'Not found'
    }

def handle_auth_request(event, context):
    """Handle login and registration requests"""
    try:
        body = json.loads(event.get('body', '{}'))
        action = body.get('action')
        
        if action == 'login':
            return handle_login(body)
        elif action == 'register':
            return handle_registration(body)
        else:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'message': 'Invalid action'
                })
            }
    except Exception as e:
        print(f"Auth error: {e}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'message': 'Server error'
            })
        }

def handle_login(body):
    """Handle user login"""
    student_id = body.get('studentId', '').strip()
    password = body.get('password', '').strip()
    
    print(f"Login attempt - Student ID: {student_id}, Password length: {len(password)}")
    
    if not student_id or not password:
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'message': 'Student ID and password required'
            })
        }
    
    try:
        # Get user from DynamoDB
        print(f"Looking up user: {student_id}")
        response = users_table.get_item(Key={'student_id': student_id})
        
        if 'Item' not in response:
            print(f"User not found: {student_id}")
            return {
                'statusCode': 401,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'message': 'Invalid Student ID or password'
                })
            }
        
        user = response['Item']
        print(f"User found: {user['full_name']}, stored password: {user['password']}")
        
        # Check password (in production, use hashed passwords)
        if user['password'] != password:
            print(f"Password mismatch - provided: '{password}', stored: '{user['password']}'")
            return {
                'statusCode': 401,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'message': 'Invalid Student ID or password'
                })
            }
        
        print(f"Login successful for: {user['full_name']}")
        # Login successful
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': True,
                'user': {
                    'student_id': user['student_id'],
                    'full_name': user['full_name'],
                    'email': user['email']
                }
            })
        }
        
    except Exception as e:
        print(f"Login error: {e}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'message': 'Login failed'
            })
        }

def handle_registration(body):
    """Handle user registration"""
    name = body.get('name', '').strip()
    email = body.get('email', '').strip()
    student_id = body.get('studentId', '').strip()
    password = body.get('password', '').strip()
    
    if not all([name, email, student_id, password]):
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'message': 'All fields are required'
            })
        }
    
    try:
        # Check if student ID already exists
        response = users_table.get_item(Key={'student_id': student_id})
        
        if 'Item' in response:
            return {
                'statusCode': 409,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'message': 'Student ID already exists'
                })
            }
        
        # Create new user
        new_user = {
            'student_id': student_id,
            'full_name': name,
            'email': email,
            'password': password,  # In production, hash this
            'status': 'active',
            'created_at': datetime.now().isoformat() + 'Z'
        }
        
        users_table.put_item(Item=new_user)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': True,
                'studentId': student_id,
                'message': 'Registration successful'
            })
        }
        
    except Exception as e:
        print(f"Registration error: {e}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'message': 'Registration failed'
            })
        }

def serve_html():
    html_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EduBot - Educational Institution</title>
    <style>
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Arial', sans-serif;
    line-height: 1.6;
    color: #333;
}

header {
    background: #2c3e50;
    color: white;
    padding: 1rem 0;
    position: fixed;
    width: 100%;
    top: 0;
    z-index: 100;
}

nav {
    display: flex;
    justify-content: space-between;
    align-items: center;
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 2rem;
}

.logo {
    font-size: 1.5rem;
    font-weight: bold;
}

nav ul {
    display: flex;
    list-style: none;
}

nav ul li {
    margin-left: 2rem;
}

nav ul li a {
    color: white;
    text-decoration: none;
    transition: color 0.3s;
}

nav ul li a:hover {
    color: #3498db;
}

main {
    margin-top: 80px;
}

.hero {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    text-align: center;
    padding: 100px 2rem;
}

.hero h1 {
    font-size: 3rem;
    margin-bottom: 1rem;
}

.hero p {
    font-size: 1.2rem;
    margin-bottom: 2rem;
}

.cta-btn {
    background: #e74c3c;
    color: white;
    padding: 12px 30px;
    border: none;
    border-radius: 5px;
    font-size: 1.1rem;
    cursor: pointer;
    transition: background 0.3s;
}

.cta-btn:hover {
    background: #c0392b;
}

.section {
    padding: 60px 2rem;
    max-width: 1200px;
    margin: 0 auto;
}

.section h2 {
    text-align: center;
    margin-bottom: 3rem;
    font-size: 2.5rem;
    color: #2c3e50;
}

.course-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 2rem;
}

.course-card {
    background: white;
    padding: 2rem;
    border-radius: 10px;
    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    text-align: center;
    transition: transform 0.3s;
}

.course-card:hover {
    transform: translateY(-5px);
}

.course-card h3 {
    color: #2c3e50;
    margin-bottom: 1rem;
}

.course-card button {
    background: #3498db;
    color: white;
    padding: 10px 20px;
    border: none;
    border-radius: 5px;
    cursor: pointer;
    margin-top: 1rem;
}

.event-list {
    display: grid;
    gap: 1rem;
}

.event-item {
    background: #f8f9fa;
    padding: 1.5rem;
    border-radius: 8px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.event-item button {
    background: #27ae60;
    color: white;
    padding: 8px 16px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
}

#chatbot-container {
    position: fixed;
    bottom: 20px;
    right: 20px;
    z-index: 1000;
    display: none;
}

#chatbot-container.logged-in {
    display: block;
}

#chat-toggle {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    background: #007bff;
    color: white;
    border: none;
    font-size: 24px;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(0,123,255,0.3);
    transition: all 0.3s ease;
}

#chat-toggle:hover {
    background: #0056b3;
    transform: scale(1.1);
}

#whatsapp-btn {
    position: absolute;
    bottom: 90px;
    right: 0;
    width: 50px;
    height: 50px;
    border-radius: 50%;
    background: #25D366;
    color: white;
    text-decoration: none;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    box-shadow: 0 4px 12px rgba(37,211,102,0.3);
    transition: all 0.3s ease;
}

#whatsapp-btn:hover {
    background: #128C7E;
    transform: scale(1.1);
    text-decoration: none;
    color: white;
}

#chat-window {
    display: none;
    position: absolute;
    bottom: 70px;
    right: 0;
    width: 380px;
    height: 550px;
    background: white;
    border-radius: 15px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    overflow: hidden;
}

#chat-header {
    background: #007bff;
    color: white;
    padding: 15px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: bold;
}

#close-chat {
    background: none;
    border: none;
    color: white;
    font-size: 20px;
    cursor: pointer;
}

#chat-messages {
    height: 350px;
    overflow-y: auto;
    padding: 15px;
    background: #f8f9fa;
}

.message {
    margin: 10px 0;
    padding: 10px 15px;
    border-radius: 18px;
    max-width: 80%;
    word-wrap: break-word;
}

.user-message {
    background: #007bff;
    color: white;
    margin-left: auto;
    text-align: right;
}

.bot-message {
    background: white;
    color: #333;
    border: 1px solid #e9ecef;
}

#quick-actions {
    padding: 10px;
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    background: #f8f9fa;
    border-top: 1px solid #e9ecef;
}

.quick-btn {
    background: #6c757d;
    color: white;
    border: none;
    padding: 6px 12px;
    border-radius: 15px;
    font-size: 12px;
    cursor: pointer;
    transition: background 0.3s;
}

.quick-btn:hover {
    background: #5a6268;
}

#chat-input {
    display: flex;
    padding: 15px;
    background: white;
    border-top: 1px solid #e9ecef;
    align-items: center;
    gap: 10px;
}

#attach-btn {
    background: #f8f9fa;
    border: 1px solid #ced4da;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    transition: background-color 0.2s;
}

#attach-btn:hover {
    background: #e9ecef;
}

#message-input {
    flex: 1;
    padding: 10px;
    border: 1px solid #ced4da;
    border-radius: 20px;
    outline: none;
}

#send-btn {
    padding: 10px 20px;
    background: #007bff;
    color: white;
    border: none;
    border-radius: 20px;
    cursor: pointer;
}

#send-btn:hover {
    background: #0056b3;
}

.modal {
    display: none;
    position: fixed;
    z-index: 2000;
    left: 0;
    top: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0,0,0,0.5);
}

.modal-content {
    background-color: white;
    margin: 10% auto;
    padding: 30px;
    border-radius: 10px;
    width: 400px;
    max-width: 90%;
    position: relative;
}

.close {
    position: absolute;
    right: 15px;
    top: 15px;
    font-size: 28px;
    font-weight: bold;
    cursor: pointer;
    color: #aaa;
}

.close:hover {
    color: #000;
}

.auth-form h2 {
    text-align: center;
    margin-bottom: 20px;
    color: #2c3e50;
}

.auth-form input {
    width: 100%;
    padding: 12px;
    margin: 10px 0;
    border: 1px solid #ddd;
    border-radius: 5px;
    box-sizing: border-box;
}

.auth-form button {
    width: 100%;
    padding: 12px;
    background: #007bff;
    color: white;
    border: none;
    border-radius: 5px;
    cursor: pointer;
    font-size: 16px;
    margin: 10px 0;
}

.auth-form button:hover {
    background: #0056b3;
}

.auth-form p {
    text-align: center;
    margin-top: 15px;
}

.auth-form a {
    color: #007bff;
    text-decoration: none;
}

.auth-form a:hover {
    text-decoration: underline;
}

.demo-credentials {
    background: #f8f9fa;
    padding: 15px;
    border-radius: 8px;
    margin-bottom: 20px;
    border: 1px solid #e9ecef;
}

.demo-credentials h4 {
    margin: 0 0 10px 0;
    color: #495057;
    font-size: 14px;
}

.demo-user {
    background: white;
    padding: 10px;
    margin: 8px 0;
    border-radius: 5px;
    cursor: pointer;
    border: 1px solid #dee2e6;
    transition: all 0.2s;
    font-size: 13px;
}

.demo-user:hover {
    background: #e3f2fd;
    border-color: #007bff;
    transform: translateY(-1px);
}

.demo-user strong {
    color: #2c3e50;
}

#user-info {
    position: fixed;
    top: 20px;
    right: 20px;
    background: white;
    padding: 10px 15px;
    border-radius: 5px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    z-index: 1500;
}

#user-info button {
    margin-left: 10px;
    padding: 5px 10px;
    background: #dc3545;
    color: white;
    border: none;
    border-radius: 3px;
    cursor: pointer;
}

@media (max-width: 768px) {
    nav {
        flex-direction: column;
        padding: 1rem;
    }

    nav ul {
        margin-top: 1rem;
    }

    nav ul li {
        margin: 0 1rem;
    }

    .hero h1 {
        font-size: 2rem;
    }

    #chat-window {
        width: 320px;
        height: 500px;
    }

    #chat-messages {
        height: 300px;
    }
}
    </style>
</head>
<body>
    <header>
        <nav>
            <div class="logo">EduBot University</div>
            <ul>
                <li><a href="#home">Home</a></li>
                <li><a href="#courses">Courses</a></li>
                <li><a href="#admissions">Admissions</a></li>
                <li><a href="#events">Events</a></li>
                <li><a href="#contact">Contact</a></li>
                <li><a href="#" onclick="openAuthModal()">Login</a></li>
            </ul>
        </nav>
    </header>

    <main>
        <section id="home" class="hero">
            <h1>Welcome to EduBot University</h1>
            <p>Your gateway to quality education and seamless registration</p>
            <button class="cta-btn" onclick="requireLogin('Get Help with Registration')">Get Help with Registration</button>
        </section>

        <section id="courses" class="section">
            <h2>Our Courses</h2>
            <div class="course-grid">
                <div class="course-card">
                    <h3>Computer Science</h3>
                    <p>CS101 - Introduction to Programming</p>
                    <button onclick="requireLoginForCourse('CS101')">Enroll Now</button>
                </div>
                <div class="course-card">
                    <h3>Mathematics</h3>
                    <p>MATH201 - Advanced Calculus</p>
                    <button onclick="requireLoginForCourse('MATH201')">Enroll Now</button>
                </div>
                <div class="course-card">
                    <h3>Physics</h3>
                    <p>PHY301 - Quantum Mechanics</p>
                    <button onclick="requireLoginForCourse('PHY301')">Enroll Now</button>
                </div>
            </div>
        </section>

        <section id="admissions" class="section">
            <h2>Admissions</h2>
            <p>Start your journey with us. Apply for admission today!</p>
            <button class="cta-btn" onclick="requireLogin('Apply for Admission')">Apply Now</button>
        </section>

        <section id="events" class="section">
            <h2>Upcoming Events</h2>
            <div class="event-list">
                <div class="event-item">
                    <h3>Tech Conference 2025</h3>
                    <p>Date: March 15, 2025</p>
                    <button onclick="requireLoginForEvent('Tech Conference 2025')">Register</button>
                </div>
                <div class="event-item">
                    <h3>Career Fair</h3>
                    <p>Date: April 10, 2025</p>
                    <button onclick="requireLoginForEvent('Career Fair')">Register</button>
                </div>
            </div>
        </section>
    </main>

    <!-- Login/Register Modal -->
    <div id="auth-modal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeAuthModal()">&times;</span>
            
            <div id="login-form" class="auth-form">
                <h2>Student Login</h2>
                
                <div class="demo-credentials">
                    <h4>Demo Accounts (Click to use):</h4>
                    <div class="demo-user" onclick="fillLogin('DEMO001', 'demo123')">
                        <strong>John Student</strong><br>
                        ID: DEMO001 | Pass: demo123
                    </div>
                    <div class="demo-user" onclick="fillLogin('DEMO002', 'password')">
                        <strong>Sarah Wilson</strong><br>
                        ID: DEMO002 | Pass: password
                    </div>
                    <div class="demo-user" onclick="fillLogin('STU2025001', 'student123')">
                        <strong>Mike Johnson</strong><br>
                        ID: STU2025001 | Pass: student123
                    </div>
                </div>
                
                <input type="text" id="studentId" placeholder="Student ID" required>
                <input type="password" id="password" placeholder="Password" required>
                <button onclick="login()">Login</button>
                <p>Don't have an account? <a href="#" onclick="showRegister()">Register here</a></p>
            </div>
            
            <div id="register-form" class="auth-form" style="display:none;">
                <h2>Student Registration</h2>
                <input type="text" id="regName" placeholder="Full Name" required>
                <input type="email" id="regEmail" placeholder="Email" required>
                <input type="text" id="regStudentId" placeholder="Student ID" required>
                <input type="password" id="regPassword" placeholder="Password" required>
                <button onclick="register()">Register</button>
                <p>Already have an account? <a href="#" onclick="showLogin()">Login here</a></p>
            </div>
        </div>
    </div>

    <!-- User Info Display -->
    <div id="user-info" style="display:none;">
        <span id="welcome-msg"></span>
        <button onclick="logout()">Logout</button>
    </div>

    <!-- Chatbot Widget -->
    <div id="chatbot-container">
        <button id="chat-toggle" onclick="toggleChat()">
            <span id="chat-icon">💬</span>
        </button>
        
        <!-- WhatsApp Button -->
        <a href="https://wa.me/14155238886?text=join%20let-closer" target="_blank" id="whatsapp-btn" title="Chat on WhatsApp">
            <span>📱</span>
        </a>
        
        <div id="chat-window">
            <div id="chat-header">
                <span>Registration Assistant</span>
                <button id="close-chat" onclick="toggleChat()">×</button>
            </div>
            
            <div id="chat-messages">
                <div class="message bot-message">
                    Hi! I'm your registration assistant. I can help with:
                    <br>• Course enrollment
                    <br>• Student admissions
                    <br>• Event registration
                    <br>• Fund applications
                    <br>• General FAQs
                    <br><br>What would you like to do?
                </div>
            </div>
            
            <div id="quick-actions">
                <button class="quick-btn" onclick="quickAction('enroll')">Enroll Course</button>
                <button class="quick-btn" onclick="quickAction('admission')">Apply Admission</button>
                <button class="quick-btn" onclick="quickAction('event')">Register Event</button>
                <button class="quick-btn" onclick="quickAction('fund')">Apply Fund</button>
            </div>
            
            <div id="chat-input">
                <input type="file" id="file-input" accept=".pdf,.jpg,.jpeg,.png" style="display: none;" onchange="handleFileSelect(event)">
                <button id="attach-btn" onclick="document.getElementById('file-input').click()" title="Upload Document">📎</button>
                <input type="text" id="message-input" placeholder="Type your message..." onkeypress="handleKeyPress(event)">
                <button id="send-btn" onclick="sendMessage()">Send</button>
            </div>
        </div>
    </div>

    <script>
let chatOpen = false;
let sessionId = 'web-' + Math.random().toString(36).substr(2, 9);
let currentUser = null;
let pendingAction = null;
let selectedFile = null;

// File handling functions
function handleFileSelect(event) {
    console.log('File selected:', event.target.files[0]);
    const file = event.target.files[0];
    if (file) {
        selectedFile = file;
        const messageInput = document.getElementById('message-input');
        messageInput.placeholder = `📎 ${file.name} selected - Type message and send`;
        messageInput.focus();
        console.log('File stored:', selectedFile.name, selectedFile.size);
    }
}

function requireLogin(action) {
    if (currentUser) {
        openChat();
        setTimeout(() => {
            addMessage('bot', `Hi ${currentUser.name}! I'm ready to help you with: ${action}`);
        }, 500);
    } else {
        pendingAction = { type: 'general', message: action };
        openAuthModal();
        showLoginMessage('Please login to access chat assistance');
    }
}

function requireLoginForCourse(courseCode) {
    if (currentUser) {
        openChat();
        setTimeout(() => {
            const input = document.getElementById('message-input');
            input.value = `I want to enroll in course ${courseCode}`;
            sendMessage();
        }, 500);
    } else {
        pendingAction = { type: 'course', courseCode };
        openAuthModal();
        showLoginMessage(`Please login to enroll in ${courseCode}`);
    }
}

function requireLoginForEvent(eventName) {
    if (currentUser) {
        openChat();
        setTimeout(() => {
            const input = document.getElementById('message-input');
            input.value = `I want to register for ${eventName}`;
            sendMessage();
        }, 500);
    } else {
        pendingAction = { type: 'event', eventName };
        openAuthModal();
        showLoginMessage(`Please login to register for ${eventName}`);
    }
}

function showLoginMessage(message) {
    const loginForm = document.getElementById('login-form');
    let existingMsg = loginForm.querySelector('.login-message');
    if (existingMsg) existingMsg.remove();
    
    const msgDiv = document.createElement('div');
    msgDiv.className = 'login-message';
    msgDiv.style.cssText = 'background: #e3f2fd; padding: 10px; border-radius: 5px; margin-bottom: 15px; color: #1976d2; text-align: center; font-size: 14px;';
    msgDiv.textContent = message;
    
    loginForm.insertBefore(msgDiv, loginForm.querySelector('input'));
}

function openAuthModal() {
    document.getElementById('auth-modal').style.display = 'block';
}

function closeAuthModal() {
    document.getElementById('auth-modal').style.display = 'none';
}

function showLogin() {
    document.getElementById('login-form').style.display = 'block';
    document.getElementById('register-form').style.display = 'none';
}

function showRegister() {
    document.getElementById('login-form').style.display = 'none';
    document.getElementById('register-form').style.display = 'block';
}

function fillLogin(studentId, password) {
    document.getElementById('studentId').value = studentId;
    document.getElementById('password').value = password;
}

async function login() {
    const studentId = document.getElementById('studentId').value;
    const password = document.getElementById('password').value;
    
    if (!studentId || !password) {
        alert('Please enter both Student ID and password');
        return;
    }
    
    try {
        console.log('Making login request...', {studentId, passwordLength: password.length});
        
        // Call backend to validate user credentials
        const response = await fetch('/demo/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                action: 'login',
                studentId: studentId,
                password: password
            })
        });
        
        console.log('Response status:', response.status);
        const result = await response.json();
        console.log('Response data:', result);
        
        if (result.success) {
            currentUser = { studentId: studentId, name: result.user.full_name };
            document.getElementById('welcome-msg').textContent = `Welcome, ${currentUser.name}!`;
            document.getElementById('user-info').style.display = 'block';
            
            document.getElementById('chatbot-container').classList.add('logged-in');
            
            closeAuthModal();
            
            document.querySelector('nav a[onclick="openAuthModal()"]').textContent = 'Account';
            
            if (pendingAction) {
                setTimeout(() => {
                    if (pendingAction.type === 'course') {
                        openChat();
                        setTimeout(() => {
                            const input = document.getElementById('message-input');
                            input.value = `I want to enroll in course ${pendingAction.courseCode}`;
                            sendMessage();
                        }, 500);
                    } else if (pendingAction.type === 'event') {
                        openChat();
                        setTimeout(() => {
                            const input = document.getElementById('message-input');
                            input.value = `I want to register for ${pendingAction.eventName}`;
                            sendMessage();
                        }, 500);
                    } else if (pendingAction.type === 'general') {
                        openChat();
                        setTimeout(() => {
                            addMessage('bot', `Hi ${currentUser.name}! I'm ready to help you with: ${pendingAction.message}`);
                        }, 500);
                    }
                    pendingAction = null;
                }, 1000);
            }
        } else {
            alert(result.message || 'Invalid Student ID or password.');
        }
    } catch (error) {
        console.error('Login error:', error);
        alert('Login error. Please try again.');
    }
}

async function register() {
    const name = document.getElementById('regName').value;
    const email = document.getElementById('regEmail').value;
    const studentId = document.getElementById('regStudentId').value;
    const password = document.getElementById('regPassword').value;
    
    if (!name || !email || !studentId || !password) {
        alert('Please fill all fields');
        return;
    }
    
    try {
        // Call backend to register user
        const response = await fetch('/demo/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                action: 'register',
                name: name,
                email: email,
                studentId: studentId,
                password: password
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            alert(`Registration successful for ${name}! Please login with Student ID: ${result.studentId}`);
            showLogin();
            document.getElementById('studentId').value = result.studentId;
            document.getElementById('password').value = password;
        } else {
            alert(result.message || 'Registration failed. Please try again.');
        }
    } catch (error) {
        console.error('Registration error:', error);
        alert('Registration error. Please try again.');
    }
}

function logout() {
    currentUser = null;
    pendingAction = null;
    
    document.getElementById('chatbot-container').classList.remove('logged-in');
    
    if (chatOpen) {
        toggleChat();
    }
    
    document.getElementById('user-info').style.display = 'none';
    document.querySelector('nav a[onclick="openAuthModal()"]').textContent = 'Login';
}

function toggleChat() {
    const chatWindow = document.getElementById('chat-window');
    const chatIcon = document.getElementById('chat-icon');
    
    chatOpen = !chatOpen;
    chatWindow.style.display = chatOpen ? 'block' : 'none';
    chatIcon.textContent = chatOpen ? '×' : '💬';
}

function openChat() {
    if (!chatOpen) {
        toggleChat();
    }
}

function handleKeyPress(event) {
    if (event.key === 'Enter') {
        sendMessage();
    }
}

async function sendMessage() {
    const input = document.getElementById('message-input');
    const message = input.value.trim();
    
    if (!message && !selectedFile) return;
    
    // Display user message
    if (selectedFile) {
        addMessage('user', `📎 ${selectedFile.name}${message ? ': ' + message : ''}`);
    } else {
        addMessage('user', message);
    }
    
    input.value = '';
    input.placeholder = 'Type your message...';
    
    addTypingIndicator();
    
    try {
        let response;
        
        if (selectedFile) {
            console.log('Processing file upload:', selectedFile.name);
            // Handle file upload
            response = await uploadDocument(selectedFile, message);
            selectedFile = null; // Clear selected file
        } else {
            // Handle regular message
            response = await simulateBotResponse(message);
        }
        
        removeTypingIndicator();
        addMessage('bot', response);
    } catch (error) {
        removeTypingIndicator();
        addMessage('bot', 'Sorry, I encountered an error. Please try again.');
        console.error('Send message error:', error);
    }
}

async function uploadDocument(file, message) {
    try {
        console.log('Starting upload for:', file.name, 'User:', currentUser?.name);
        
        // Check if user is logged in for name verification
        if (!currentUser) {
            return "Please log in first so I can verify your document against your profile name.";
        }
        
        console.log('Converting file to base64...');
        // Convert file to base64
        const fileData = await fileToBase64(file);
        console.log('File converted, size:', fileData.length);
        
        console.log('Making upload request...');
        const response = await fetch('/demo/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                fileData: fileData,
                fileName: file.name,
                userName: currentUser.name,
                message: message || 'Document verification request',
                sessionId: sessionId
            })
        });
        
        console.log('Upload response status:', response.status);
        const data = await response.json();
        console.log('Upload response data:', data);
        return data.response || 'Document processed successfully';
    } catch (error) {
        console.error('Upload error:', error);
        return 'Sorry, there was an error processing your document. Please try again.';
    }
}

function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => {
            // Remove the data:image/jpeg;base64, prefix
            const base64 = reader.result.split(',')[1];
            resolve(base64);
        };
        reader.onerror = error => reject(error);
    });
}

function addMessage(sender, text) {
    const messages = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;
    messageDiv.innerHTML = text;
    messages.appendChild(messageDiv);
    messages.scrollTop = messages.scrollHeight;
}

function addTypingIndicator() {
    const messages = document.getElementById('chat-messages');
    const typingDiv = document.createElement('div');
    typingDiv.id = 'typing-indicator';
    typingDiv.className = 'message bot-message';
    typingDiv.innerHTML = 'Assistant is typing...';
    messages.appendChild(typingDiv);
    messages.scrollTop = messages.scrollHeight;
}

function removeTypingIndicator() {
    const typing = document.getElementById('typing-indicator');
    if (typing) {
        typing.remove();
    }
}

function quickAction(action) {
    const actions = {
        'enroll': 'I want to enroll in a course',
        'admission': 'I want to apply for admission',
        'event': 'I want to register for an event',
        'fund': 'I want to apply for student funding'
    };
    
    const input = document.getElementById('message-input');
    input.value = actions[action];
    sendMessage();
}

async function simulateBotResponse(message) {
    try {
        const response = await fetch('/demo/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                message: message,
                sessionId: sessionId,
                userName: currentUser ? currentUser.name : null
            })
        });
        
        const data = await response.json();
        
        if (currentUser && data.response) {
            return data.response.replace(/Hello!/g, `Hello ${currentUser.name}!`);
        }
        
        return data.response || 'Sorry, I encountered an error. Please try again.';
    } catch (error) {
        console.error('API Error:', error);
        return 'Sorry, I\\'m having trouble connecting. Please try again.';
    }
}

document.addEventListener('DOMContentLoaded', function() {
    console.log('EduBot Registration System Loaded');
});
    </script>
</body>
</html>'''
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'text/html'},
        'body': html_content
    }
