# AI Study Planner

An AI-powered web application designed to help students organize their academic activities, create personalized study plans, prepare for assessments, and track their learning progress.

## About the Project

The **AI Study Planner** is a web-based academic planning system that helps students manage their subjects, topics, study sessions, and examinations in one place.

The application uses AI to assist with syllabus analysis, topic generation, study planning, and learning recommendations. It also provides assessment facilities and progress tracking to help students improve their academic productivity.

The main goal of this project is to make studying more organized, efficient, and personalized.

## Features

### Student Dashboard
- View academic information and study activities.
- Access important modules through the sidebar.
- Navigate between different sections of the application.

### Subject and Topic Management
- Add and manage academic subjects.
- Organize subjects into topics.
- View topic difficulty and importance.

### AI-Based Syllabus Processing
- Upload syllabus PDF files.
- Extract syllabus text.
- Generate topics from the uploaded syllabus using AI.

### Study Planning
- Generate study plans based on academic topics.
- Organize study activities.
- Manage upcoming examinations.

### Study Session Tracking
- Start and stop study sessions.
- Track study duration using a timer.
- View study-session history.

### Assessments
- Theory-based assessments.
- Practical programming assessments.
- Question generation and assessment attempts.
- View assessment results and performance.

### Notes and Resources
- Manage study notes.
- Organize learning resources.
- Access study materials.

### Progress Tracking
- Monitor study activities.
- View available academic progress information.
- Track assessment performance.

### Admin Dashboard
- Access administrative features.
- Manage application settings.
- Control the application theme.

> Some features are under development. Their availability may depend on the current project version.

## Technologies Used

### Frontend
- HTML5
- CSS3
- JavaScript
- Jinja2 Templates
- Responsive UI Design

### Backend
- Python
- FastAPI
- SQLAlchemy
- Starlette Session Middleware

### Database
- MySQL

### AI Integration
- Groq API for AI-powered features

### Development Tools
- Visual Studio Code
- Git
- GitHub
- MySQL Workbench
- Python Virtual Environment

## Project Structure

```text
AI-Study-Planner/
│
├── app/
│   ├── main.py
│   │
│   ├── routes/
│   │   ├── users.py
│   │   ├── subjects.py
│   │   └── assessments.py
│   │
│   ├── services/
│   │
│   ├── templates/
│   │   ├── dashboard.html
│   │   ├── subjects.html
│   │   ├── study_plan.html
│   │   ├── exams.html
│   │   ├── notes.html
│   │   ├── resources.html
│   │   ├── study_progress.html
│   │   ├── assessments.html
│   │   └── assessment_history.html
│   │
│   └── static/
│       ├── css/
│       ├── js/
│       └── images/
│
├── requirements.txt
├── README.md
└── .gitignore
```

*The structure above is a simplified overview. The actual repository may contain additional route files, templates, and services.*

## Installation and Setup

Follow these steps to run the project locally.

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/AI-Study-Planner.git
```

Navigate to the project directory:

```bash
cd AI-Study-Planner
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
```

Activate the virtual environment on Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure the Database

Install and start MySQL.

Create a database:

```sql
CREATE DATABASE study_plan;
```

Configure the MySQL connection details in the application's configuration or environment variables.

Example configuration:

```env
DATABASE_URL=mysql+pymysql://username:password@localhost/study_plan
```

Replace the username and password with your own MySQL credentials.

### 5. Configure API Keys

For AI-powered features, configure the required Groq API key in the appropriate environment variable or application configuration.

Example:

```env
GROQ_API_KEY=your_groq_api_key
```

**Important:** Do not upload your actual API keys, database passwords, or `.env` file to GitHub.

### 6. Run the Application

Start the FastAPI application:

```bash
uvicorn app.main:app --reload
```

Open the application in your browser:

```text
http://127.0.0.1:8000
```

FastAPI API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

## Application Workflow

1. The student registers or logs into the application.
2. The student adds academic subjects.
3. The student uploads a syllabus PDF.
4. The application extracts syllabus information.
5. AI assists in generating topics and study-related content.
6. The student organizes study activities and examination preparation.
7. The student starts and stops study sessions to track learning time.
8. The student attempts theory or practical assessments.
9. Available progress information and assessment results can be reviewed.

## Testing

The project includes frontend UI testing of the implemented modules.

Testing covers:

- Login and registration interfaces.
- Dashboard navigation.
- Subject management.
- Study plan interface.
- Study-session controls.
- Quiz interface.
- Exams interface.
- Notes and resources.
- Progress interface.
- Admin dashboard.
- Responsive UI behavior.
- Theme consistency.
- Assessments and Assessment History.

The frontend testing report documents the test cases, expected results, observed results, and identified UI issues.

## Project Objective

The objective of AI Study Planner is to provide students with an intelligent and organized platform that supports academic planning, examination preparation, and continuous learning improvement.


