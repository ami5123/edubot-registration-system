"""
Application Data Management for EduBot University
Simple in-memory storage for demo purposes
"""
import boto3
from datetime import datetime

# Initialize DynamoDB for persistent storage
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
applications_table = dynamodb.Table('whatsapp-loan-demo-applications')

# Demo application data for our test users
APPLICATION_DATA = {
    "John Student": {
        "student_id": "DEMO001",
        "program": "Computer Science",
        "submitted_date": "2025-10-15",
        "status": "Under Review",
        "progress": 75,
        "documents": {
            "ID Document": {"status": "verified", "uploaded": "2025-10-15"},
            "Matric Certificate": {"status": "verified", "uploaded": "2025-10-16"},
            "Income Proof": {"status": "pending", "uploaded": "2025-10-17"},
            "Bank Statements": {"status": "missing", "uploaded": None}
        },
        "next_steps": "Please upload your 3-month bank statements to complete your application."
    },
    "Sarah Wilson": {
        "student_id": "DEMO002", 
        "program": "Business Administration",
        "submitted_date": "2025-10-12",
        "status": "Approved",
        "progress": 100,
        "documents": {
            "ID Document": {"status": "verified", "uploaded": "2025-10-12"},
            "Matric Certificate": {"status": "verified", "uploaded": "2025-10-12"},
            "Income Proof": {"status": "verified", "uploaded": "2025-10-13"},
            "Bank Statements": {"status": "verified", "uploaded": "2025-10-14"}
        },
        "next_steps": "Congratulations! Your application has been approved. Check your email for enrollment details."
    },
    "Mike Johnson": {
        "student_id": "STU2025001",
        "program": "Engineering", 
        "submitted_date": "2025-10-20",
        "status": "Documents Required",
        "progress": 25,
        "documents": {
            "ID Document": {"status": "verified", "uploaded": "2025-10-20"},
            "Matric Certificate": {"status": "missing", "uploaded": None},
            "Income Proof": {"status": "missing", "uploaded": None},
            "Bank Statements": {"status": "missing", "uploaded": None}
        },
        "next_steps": "Please upload your Matric Certificate, Income Proof, and Bank Statements."
    },
    "amitha lakkakula": {
        "student_id": "STU20251022151204",
        "program": "Data Science", 
        "submitted_date": "2025-10-22",
        "status": "New Application",
        "progress": 0,
        "documents": {
            "ID Document": {"status": "missing", "uploaded": None},
            "Matric Certificate": {"status": "missing", "uploaded": None},
            "Income Proof": {"status": "missing", "uploaded": None},
            "Bank Statements": {"status": "missing", "uploaded": None}
        },
        "next_steps": "Welcome! Please start by uploading your ID Document to begin the application process."
    }
}

def get_application_status(user_name):
    """Get application status for a user - check DynamoDB first, then fallback to static data"""
    try:
        # Try to get from DynamoDB first
        response = applications_table.get_item(Key={'user_name': user_name})
        if 'Item' in response:
            return response['Item']
    except Exception as e:
        print(f"DynamoDB error: {e}")
    
    # Fallback to static data
    return APPLICATION_DATA.get(user_name)

def update_document_status(user_name, document_type, verification_result):
    """Update document status when a document is uploaded and verified"""
    try:
        # Get current application data
        app_data = get_application_status(user_name)
        if not app_data:
            # Create new application if doesn't exist
            app_data = create_default_application(user_name, "NEW_USER")
        
        # Update document status based on verification
        if verification_result['name_verified']:
            app_data['documents'][document_type] = {
                "status": "verified",
                "uploaded": datetime.now().strftime("%Y-%m-%d")
            }
        else:
            app_data['documents'][document_type] = {
                "status": "rejected",
                "uploaded": datetime.now().strftime("%Y-%m-%d")
            }
        
        # Recalculate progress
        total_docs = len(app_data['documents'])
        verified_docs = sum(1 for doc in app_data['documents'].values() if doc['status'] == 'verified')
        app_data['progress'] = int((verified_docs / total_docs) * 100)
        
        # Update status based on progress
        if app_data['progress'] == 100:
            app_data['status'] = "Under Review"
            app_data['next_steps'] = "All documents submitted! Your application is under review."
        elif app_data['progress'] >= 75:
            app_data['status'] = "Nearly Complete"
            missing_docs = [doc_name for doc_name, doc_info in app_data['documents'].items() 
                          if doc_info['status'] == 'missing']
            app_data['next_steps'] = f"Almost done! Please upload: {', '.join(missing_docs)}"
        elif app_data['progress'] >= 25:
            app_data['status'] = "In Progress"
            missing_docs = [doc_name for doc_name, doc_info in app_data['documents'].items() 
                          if doc_info['status'] == 'missing']
            app_data['next_steps'] = f"Good progress! Still need: {', '.join(missing_docs)}"
        else:
            app_data['status'] = "Documents Required"
            app_data['next_steps'] = "Please upload your required documents to continue."
        
        # Save to DynamoDB
        app_data['user_name'] = user_name
        app_data['last_updated'] = datetime.now().isoformat()
        applications_table.put_item(Item=app_data)
        
        # Also update static data for immediate access
        APPLICATION_DATA[user_name] = app_data
        
        return True
        
    except Exception as e:
        print(f"Error updating document status: {e}")
        return False

def classify_document_type(file_name, analysis_result):
    """Classify document type based on filename and content analysis"""
    file_name_lower = file_name.lower()
    
    if 'id' in file_name_lower or 'identity' in file_name_lower:
        return "ID Document"
    elif 'matric' in file_name_lower or 'certificate' in file_name_lower:
        return "Matric Certificate"
    elif 'income' in file_name_lower or 'salary' in file_name_lower or 'payslip' in file_name_lower:
        return "Income Proof"
    elif 'bank' in file_name_lower or 'statement' in file_name_lower:
        return "Bank Statements"
    else:
        # Default to Income Proof for payslips
        return "Income Proof"

def get_application_by_student_id(student_id):
    """Get application status by student ID (for WhatsApp)"""
    for name, data in APPLICATION_DATA.items():
        if data["student_id"] == student_id:
            return name, data
    return None, None

def create_default_application(user_name, student_id):
    """Create default application for new users"""
    APPLICATION_DATA[user_name] = {
        "student_id": student_id,
        "program": "General Studies", 
        "submitted_date": "2025-10-29",
        "status": "New Application",
        "progress": 0,
        "documents": {
            "ID Document": {"status": "missing", "uploaded": None},
            "Matric Certificate": {"status": "missing", "uploaded": None},
            "Income Proof": {"status": "missing", "uploaded": None},
            "Bank Statements": {"status": "missing", "uploaded": None}
        },
        "next_steps": "Welcome! Please start by uploading your ID Document to begin the application process."
    }
    return APPLICATION_DATA[user_name]

def format_status_for_web(user_name):
    """Format application status for web chat"""
    app_data = get_application_status(user_name)
    if not app_data:
        return "No application found for your account. Please contact admissions."
    
    # Format documents status
    doc_status = []
    for doc_name, doc_info in app_data["documents"].items():
        if doc_info["status"] == "verified":
            doc_status.append(f"✅ {doc_name} - Verified")
        elif doc_info["status"] == "pending":
            doc_status.append(f"⏳ {doc_name} - Pending Review")
        elif doc_info["status"] == "rejected":
            doc_status.append(f"❌ {doc_name} - Rejected (reupload needed)")
        else:
            doc_status.append(f"❌ {doc_name} - Missing")
    
    status_message = f"""📋 **Application Status for {user_name}**

🎓 **Program**: {app_data['program']}
📅 **Submitted**: {app_data['submitted_date']}
📊 **Status**: {app_data['status']}
📈 **Progress**: {app_data['progress']}% Complete

**Documents Submitted:**
{chr(10).join(doc_status)}

**Next Steps:**
{app_data['next_steps']}"""

    return status_message

def format_status_for_whatsapp(user_name):
    """Format application status for WhatsApp (more compact)"""
    app_data = get_application_status(user_name)
    if not app_data:
        return "No application found. Please check your Student ID."
    
    # Count document statuses
    verified = sum(1 for doc in app_data["documents"].values() if doc["status"] == "verified")
    total = len(app_data["documents"])
    
    status_message = f"""📋 *Application Status*

Program: {app_data['program']}
Status: {app_data['status']}
Progress: {app_data['progress']}% ({verified}/{total} docs)

Documents:"""
    
    for doc_name, doc_info in app_data["documents"].items():
        if doc_info["status"] == "verified":
            status_message += f"\n✅ {doc_name}"
        elif doc_info["status"] == "pending":
            status_message += f"\n⏳ {doc_name}"
        elif doc_info["status"] == "rejected":
            status_message += f"\n❌ {doc_name} (rejected)"
        else:
            status_message += f"\n❌ {doc_name}"
    
    status_message += f"\n\n{app_data['next_steps']}"
    
    return status_message
