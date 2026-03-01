# 🎓 Pioneer — University Support System

A full-stack university helpdesk web application where students can submit queries and admins can manage, categorize, and resolve them. Queries are automatically classified by category and priority using Google Gemini AI, with a rule-based fallback.

---

## 📸 Pages Overview

 Page  Route  Description 
--------------------------
 Role Selector  ``  Choose between Student or Admin 
 Student Portal  `student`  Register, login, submit & track queries 
 Admin Login  `admin-login-page`  Admin authentication 
 Admin Dashboard  `admin-page`  Manage all queries, students & stats 

---

## ✨ Features

### Student
- Register and log in securely
- Submit queries (auto-classified by AI)
- View query history with status, category, and priority
- Session persists across browser refresh

### Admin
- Secure admin-only login
- Dashboard with live stats (total queries, pending, in progress, resolved)
- Category and priority breakdown charts
- Filter queries by status, category, or priority
- Update query status inline (Pending → In Progress → Resolved)
- Delete queries
- View all students and their individual query history
- Session persists across browser refresh

### AI Classification
- Uses Google Gemini 2.0 Flash to auto-detect
  - Category Finance, Academics, Technical, Hostel, Admin, Library, General
  - Priority High, Medium, Low
- Falls back to keyword-based rule engine if AI is unavailable

---

## 🗂️ Project Structure

```
your_project
├── app.py                  ← Flask backend
├── .env                    ← Your secret API key (never commit this)
├── .gitignore              ← Keeps .env and DB out of git
├── requirements.txt        ← Python dependencies
├── queries.db              ← SQLite database (auto-created)
└── templates
    ├── role1.html          ← Role selector page
    ├── student.html        ← Student portal
    ├── admin_login.html    ← Admin login page
    └── admin.html          ← Admin dashboard
```

---

## ⚙️ Setup Instructions

### 1. Clone or download the project

```bash
git clone httpsgithub.comyourusernamepioneer-support.git
cd pioneer-support
```

### 2. Install dependencies

```bash
pip install flask python-dotenv google-generativeai werkzeug
```

### 3. Create your `.env` file

Create a file named `.env` in the root of your project

```
GEMINI_API_KEY=your_gemini_api_key_here
```

 Get a free API key from [httpsaistudio.google.com](httpsaistudio.google.com)

 If you skip this step, the app will still work using rule-based classification.

### 4. Run the app

```bash
python app.py
```

### 5. Open in browser

```
httplocalhost5000
```

---

## 🔐 Default Admin Credentials

 Field  Value 
--------------
 Username  `admin` 
 Password  `admin123` 

 These are auto-created on first run. Change the password after setup.

---

## 🧠 How Query Classification Works

When a student submits a query, the system

1. Sends the query text to Gemini 2.0 Flash with a structured prompt
2. Gemini returns a JSON response with `category` and `priority`
3. If Gemini is unavailable or the API key is missing, the app falls back to keyword matching

### Categories
`Finance` · `Academics` · `Technical` · `Hostel` · `Admin` · `Library` · `General`

### Priority Levels
 Priority  Trigger Keywords 
---------------------------
 🔴 High  urgent, deadline, tomorrow, asap, emergency, today 
 🟡 Medium  everything else 
 🟢 Low  whenever, no rush, general inquiry, just wondering 

---

## 📝 Example Queries to Test

High Priority
- My exam hall ticket is not generated and the exam is tomorrow.
- Fee payment was deducted but portal still shows dues. Need this fixed immediately.

Medium Priority
- I want to apply for revaluation of my Mathematics paper.
- My attendance is showing 68% but I attended all lectures.

Low Priority
- Just wondering what elective courses are available next semester.
- No rush, but I'd like to know the hostel room change procedure.

---

## 🛡️ Security Features

- Passwords hashed with Werkzeug (PBKDF2)
- Session cookie is `HttpOnly` and `SameSite=Lax`
- Rate limiting max 5 submissions per minute per user
- Prompt injection detection on query input
- API key loaded from `.env` only — never hardcoded
- Admin routes protected by role-based decorators

---

## 🗄️ Database Schema

### `users`
 Column  Type  Description 
---------------------------
 id  INTEGER  Primary key 
 username  TEXT  Unique username 
 email  TEXT  Unique email 
 password  TEXT  Hashed password 
 role  TEXT  `student` or `admin` 

### `queries`
 Column  Type  Description 
---------------------------
 id  INTEGER  Primary key 
 user_id  INTEGER  Foreign key → users 
 query_text  TEXT  The submitted query 
 category  TEXT  AI-assigned category 
 priority  TEXT  AI-assigned priority 
 status  TEXT  Pending  In Progress  Resolved 
 created_at  TIMESTAMP  Submission time 

---

## 🔧 API Endpoints

### Auth
 Method  Endpoint  Description 
-------------------------------
 POST  `register`  Register a new student 
 POST  `login`  Student login 
 POST  `apilogout`  Student logout 
 GET  `apime`  Get current session user 
 POST  `admin-login`  Admin login 
 GET  `logout`  Admin logout (redirect) 

### Student
 Method  Endpoint  Description 
-------------------------------
 POST  `submit`  Submit a query 
 GET  `studentqueries`  Get own queries (paginated) 

### Admin
 Method  Endpoint  Description 
-------------------------------
 GET  `admindashboard`  Stats and counts 
 GET  `adminqueries`  All queries (filterable) 
 GET  `adminstudents`  All students 
 GET  `adminstudentid`  Student detail + queries 
 PUT  `adminupdate-status`  Update query status 
 DELETE  `admindelete-queryid`  Delete a query 

---

## 📦 Requirements

```
flask
python-dotenv
google-generativeai
werkzeug
```

Install all at once
```bash
pip install flask python-dotenv google-generativeai werkzeug
```

---

## 🚀 Future Improvements

- Email notifications when query status changes
- Admin replycomments on queries
- Student can closereopen their own queries
- Export queries to CSV
- Darklight theme toggle

---

## 📄 License

This project is for educational purposes. Feel free to use and modify it.

---

 Built with Flask · SQLite · Google Gemini AI