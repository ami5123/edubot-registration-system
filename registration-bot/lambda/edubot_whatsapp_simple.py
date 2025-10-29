import json
import boto3
import urllib.parse
import urllib.request
import re
import uuid
import base64
import os
from datetime import datetime
from application_data import format_status_for_whatsapp, get_application_by_student_id, update_document_status, classify_document_type

# Initialize AWS clients
lex_client = boto3.client('lexv2-runtime', region_name='us-east-1')
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
textract = boto3.client('textract', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# DynamoDB table
applications_table = dynamodb.Table('whatsapp-loan-demo-applications')

# Twilio credentials from environment variables
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', 'your_account_sid_here')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', 'your_auth_token_here')

def lambda_handler(event, context):
    print(f"Received event: {json.dumps(event)}")
    
    try:
        if event['httpMethod'] == 'POST':
            # Parse Twilio webhook data
            body = event.get('body', '')
            print(f"Request body: {body}")
            
            parsed_data = urllib.parse.parse_qs(body)
            print(f"Parsed data: {parsed_data}")
            
            from_number = parsed_data.get('From', [''])[0]
            message_body = parsed_data.get('Body', [''])[0]
            
            print(f"From: {from_number}, Message: {message_body}")
            
            # Check if this is a media message (document upload)
            num_media = int(parsed_data.get('NumMedia', ['0'])[0])
            print(f"Number of media files: {num_media}")
            
            if num_media > 0:
                # Handle document upload
                bot_response = handle_document_upload(parsed_data, from_number)
            else:
                # Handle regular text message
                bot_response = process_with_hybrid_ai(message_body, from_number)
            
            print(f"Bot response: {bot_response}")
            
            # Create TwiML response
            twiml_response = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{bot_response}</Message>
</Response>'''
            
            print(f"TwiML response: {twiml_response}")
            
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/xml'},
                'body': twiml_response
            }
        
        elif event['httpMethod'] == 'GET':
            print("GET request received")
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'text/plain'},
                'body': 'EduBot WhatsApp Webhook Active'
            }
            
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        error_response = '''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>Sorry, I'm having technical difficulties. Please try again later.</Message>
</Response>'''
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/xml'},
            'body': error_response
        }

def process_with_hybrid_ai(message, session_id):
    """Process with hybrid Lex + Bedrock - same logic as web"""
    try:
        # Check if user is asking for application status
        if is_status_request(message):
            return handle_status_request(message)
        
        # Check if user provided a student ID (for status lookup)
        if re.match(r'^(DEMO\d+|STU\d+)$', message.upper().strip()):
            return handle_student_id_lookup(message.strip())
        
        clean_session_id = session_id.replace('+', '').replace(':', '_').replace('whatsapp', 'wa')[:50]
        
        # Call Lex first
        response = lex_client.recognize_text(
            botId='QCDXUQVV6M',
            botAliasId='TSTALIASID',
            localeId='en_US',
            sessionId=clean_session_id,
            text=message
        )
        
        # Use Lex response or fallback to Bedrock
        if 'messages' in response and response['messages']:
            lex_response = response['messages'][0]['content']
            
            # Only use Bedrock for very low confidence or FallbackIntent
            if should_use_bedrock(message, response):
                return handle_with_bedrock(message)
            else:
                return format_for_whatsapp(lex_response)
        else:
            return handle_with_bedrock(message)
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return "I can help you with EduBot University. What would you like to know?"

def should_use_bedrock(user_input, lex_response):
    """Only use Bedrock for very low confidence, fallback, or general help"""
    
    # Always use Bedrock for general help queries
    help_keywords = ['help', 'what can you do', 'how can you help', 'what do you do']
    if any(keyword in user_input.lower() for keyword in help_keywords):
        return True
    
    # Always use Bedrock for application process queries (not status checking)
    process_keywords = ['application process', 'how to apply', 'how do i apply', 'registration process', 'how to register', 'start application', 'lets start', 'begin application', 'start the application', 'how can i start', 'how do i start', 'i want to apply', 'just want to apply', 'apply for it', 'how to upload', 'upload documents', 'apply for a course', 'want to apply for course', 'computer science', 'business administration', 'engineering', 'liberal arts']
    if any(keyword in user_input.lower() for keyword in process_keywords):
        return True
    
    # Check Lex confidence
    confidence = lex_response.get('nluIntentConfidence', {}).get('score', 1.0)
    if confidence < 0.5:
        return True
    
    # Check if FallbackIntent
    if 'sessionState' in lex_response:
        intent_name = lex_response['sessionState']['intent']['name']
        if intent_name == 'FallbackIntent':
            return True
    
    return False

def handle_with_bedrock(user_input):
    """Simple Bedrock handling"""
    try:
        # Special handling for help queries
        if any(keyword in user_input.lower() for keyword in ['help', 'what can you do']):
            context = f"""You are an assistant for EduBot University. The user asked for help. Provide a brief overview of what you can help with.

Available services:
- Course enrollment and program information
- Admissions process and requirements  
- Financial aid and funding applications
- Document upload and verification
- Application status checks

Keep the response short and direct for WhatsApp.

User: {user_input}"""
        
        # Special handling for specific course applications
        elif any(course in user_input.lower() for course in ['computer science', 'business administration', 'engineering', 'liberal arts']):
            # Detect which course they mentioned
            course_name = ""
            if 'computer science' in user_input.lower():
                course_name = "Computer Science (4 years)"
            elif 'business' in user_input.lower():
                course_name = "Business Administration (3 years)"
            elif 'engineering' in user_input.lower():
                course_name = "Engineering (4 years)"
            elif 'liberal arts' in user_input.lower():
                course_name = "Liberal Arts (3 years)"
            
            context = f"""You are an assistant for EduBot University. The user wants to apply for {course_name}. Provide specific application steps for this program.

Steps for {course_name}:
1. Visit application portal
2. Fill application form
3. Pay R500 fee
4. Upload: SA ID, Matric Certificate, Transcripts
5. Wait for review (2-3 weeks)

Deadline: December 15
Website: https://wqgugyg29d.execute-api.us-east-1.amazonaws.com/demo/login

Be encouraging and helpful. Keep response short for WhatsApp.

User: {user_input}"""

        # Special handling for general application queries
        elif any(keyword in user_input.lower() for keyword in ['application process', 'how to apply', 'registration process', 'start application', 'lets start', 'begin application', 'how can i start', 'how do i start', 'i want to apply', 'just want to apply', 'apply for it', 'apply for a course', 'want to apply for course']):
            context = f"""You are an assistant for EduBot University. The user wants to apply for a course. Be conversational and ask which course they're interested in.

Available programs:
- Computer Science (4 years)
- Business Administration (3 years)  
- Engineering (4 years)
- Liberal Arts (3 years)

Ask them which program interests them, then provide specific next steps. Keep it short and conversational for WhatsApp.

User: {user_input}"""
            context = f"""You are an assistant for EduBot University. The user needs help with uploading documents.

Explain document upload process:
1. Go to: https://wqgugyg29d.execute-api.us-east-1.amazonaws.com/demo/login
2. Click "Upload Documents" button
3. Select your files (SA ID, Matric Certificate, Transcripts)
4. AI will verify documents automatically
5. Get instant feedback on document status

Required: Documents must be in your name for verification.

Keep response short and clear for WhatsApp.

User: {user_input}"""
        else:
            context = f"""You are an assistant for EduBot University in South Africa. Be direct and helpful.

Programs: Computer Science, Business Administration, Engineering, Liberal Arts
Application fee: R500
Required documents: SA ID, Matric Certificate, Transcripts

Keep responses short for WhatsApp. Don't introduce yourself.

User: {user_input}"""
        
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 80,  # Much shorter for WhatsApp
            "temperature": 0.6,
            "messages": [
                {
                    "role": "user",
                    "content": context
                }
            ]
        }
        
        response = bedrock.invoke_model(
            body=json.dumps(request_body),
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            accept="application/json",
            contentType="application/json"
        )
        
        response_body = json.loads(response.get('body').read())
        bedrock_response = response_body['content'][0]['text'].strip()
        
        # Clean response
        bedrock_response = clean_response(bedrock_response)
        
        return format_for_whatsapp(bedrock_response)
        
    except Exception as e:
        print(f"Bedrock error: {e}")
        return "I can help with EduBot University information. What do you need?"

def clean_response(response):
    """Remove introductions and stage directions"""
    
    # Remove stage directions
    response = re.sub(r'\*[^*]*\*', '', response)
    
    # Remove common introductions
    intro_patterns = [
        r"Hello[^.!]*EduBot University[^.!]*[.!]?\s*",
        r"Hi[^.!]*EduBot University[^.!]*[.!]?\s*",
        r"I'm[^.!]*assistant[^.!]*[.!]?\s*"
    ]
    
    for pattern in intro_patterns:
        response = re.sub(pattern, '', response, flags=re.IGNORECASE)
    
    response = re.sub(r'\s+', ' ', response).strip()
    
    if response and not response[0].isupper():
        response = response[0].upper() + response[1:]
    
    return response

def format_for_whatsapp(response):
    """Format for WhatsApp limits"""
    # WhatsApp has strict message limits - keep it very short
    if len(response) > 800:
        response = response[:800] + "..."
    
    return response.replace("\\n", "\n")

def handle_document_upload(parsed_data, from_number):
    """Handle document upload from WhatsApp with Textract verification"""
    try:
        # Get media URL from Twilio
        media_url = parsed_data.get('MediaUrl0', [''])[0]
        media_type = parsed_data.get('MediaContentType0', [''])[0]
        
        if not media_url:
            return "❌ No document received. Please try uploading again."
        
        # Only process images and PDFs
        if not any(t in media_type.lower() for t in ['image', 'pdf']):
            return "❌ Please upload images (JPG, PNG) or PDF files only."
        
        # Download the media file
        file_data = download_media_from_twilio(media_url)
        if not file_data:
            return """❌ **Document Download Failed**

Could not access your document. This might be because:
• Twilio authentication is not configured
• Document format not supported
• Network connectivity issue

**Please try:**
1. Use web interface: https://wqgugyg29d.execute-api.us-east-1.amazonaws.com/demo/login
2. Or contact support for WhatsApp document upload setup"""
        
        # Extract user name from phone number (get from WhatsApp profile or registration)
        user_name = parsed_data.get('ProfileName', [''])[0] or "Student"  # Use WhatsApp profile name
        document_name = f"Document_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        print(f"User name from WhatsApp: {user_name}")
        
        # Analyze document with Textract
        analysis_result = analyze_and_verify_document(file_data, document_name, user_name)
        
        # Update application status based on verification result
        document_type = classify_document_type(document_name, analysis_result)
        update_success = update_document_status(user_name, document_type, analysis_result)
        
        # Generate response based on analysis
        if analysis_result['name_verified']:
            # Store successful verification
            doc_id = str(uuid.uuid4())
            store_document_info(from_number, doc_id, document_name, analysis_result['analysis'])
            
            return f"""✅ **Document Accepted!**

📄 **Type**: {document_type}
📊 **Confidence**: {analysis_result['analysis']['confidence']}%
👤 **Name Match**: Verified

Your application status has been updated! Send "application status" to check your progress."""
👤 **Names Found**: {', '.join(analysis_result['found_names'][:2])}

{analysis_result['analysis']['details']}

**Status**: Document added to your application

**Text Sample**: "{analysis_result['extracted_text'][:100]}..."

Upload more documents or ask about your application status!"""
        
        else:
            return f"""❌ **Document Rejected**

📄 **Type**: {document_type}
📊 **Confidence**: {analysis_result['analysis']['confidence']}%
🔍 **Issue**: Name verification failed

**Found Names**: {', '.join(analysis_result['found_names']) if analysis_result['found_names'] else 'No clear names detected'}

**Why Rejected**:
• Document must contain your full name
• Text must be clearly readable
• Document must be official/authentic

Your application status has been updated. Send "application status" to check your progress."""

**Required Documents**:
• SA Identity Document
• Matric Certificate
• Academic Transcripts
• Income Proof

**Tips**:
• Use good lighting
• Ensure text is clear
• Document must be in your name

Try uploading a clearer document!"""
        
    except Exception as e:
        print(f"Document upload error: {e}")
        return "❌ Document processing failed. Please try uploading again."

def download_media_from_twilio(media_url):
    """Download media file from Twilio with authentication"""
    try:
        # Check if auth token is configured
        if TWILIO_AUTH_TOKEN == 'not_configured':
            print("Twilio auth token not configured")
            return None
            
        # Create authenticated request
        credentials = f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        # Create request with authentication
        request = urllib.request.Request(media_url)
        request.add_header("Authorization", f"Basic {encoded_credentials}")
        
        with urllib.request.urlopen(request) as response:
            if response.status == 200:
                return response.read()
        return None
    except Exception as e:
        print(f"Media download error: {e}")
        return None

def analyze_and_verify_document(file_bytes, document_name, user_name):
    """Use AWS Textract to analyze document and verify name"""
    try:
        # Call Textract to extract text
        response = textract.detect_document_text(
            Document={'Bytes': file_bytes}
        )
        
        # Extract all text from the document
        extracted_text = ""
        for block in response['Blocks']:
            if block['BlockType'] == 'LINE':
                extracted_text += block['Text'] + " "
        
        # Verify name in document (enhanced for WhatsApp)
        name_verification = verify_name_in_text(extracted_text, user_name)
        
        # Classify document type
        document_analysis = classify_document_by_content(extracted_text.lower(), document_name)
        
        return {
            'name_verified': name_verification['verified'],
            'found_names': name_verification['found_names'],
            'analysis': document_analysis,
            'extracted_text': extracted_text[:200] + "..." if len(extracted_text) > 200 else extracted_text
        }
        
    except Exception as e:
        print(f"Textract error: {e}")
        return {
            'name_verified': False,
            'found_names': [],
            'analysis': {
                'detected_type': 'Unknown Document',
                'confidence': 0,
                'details': 'Could not analyze document',
                'status': 'Analysis failed'
            },
            'extracted_text': ''
        }

def verify_name_in_text(text, user_name):
    """Verify if user's name appears in the extracted text - strict matching"""
    try:
        print(f"Verifying name '{user_name}' in text: {text[:200]}...")
        
        # Clean and normalize names
        user_name_clean = clean_name_for_verification(user_name)
        text_clean = clean_name_for_verification(text)
        
        print(f"Cleaned user name: '{user_name_clean}'")
        print(f"Cleaned text sample: '{text_clean[:100]}...'")
        
        # Split user name into parts
        user_name_parts = user_name_clean.split()
        
        # Find potential names in text (words that start with capital letters)
        potential_names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        found_names = [clean_name_for_verification(name) for name in potential_names]
        
        print(f"User name parts: {user_name_parts}")
        print(f"Found names in document: {found_names}")
        
        # Strict verification: Check if user's name parts appear in document
        name_found = False
        
        if len(user_name_parts) >= 2:
            # For full names, require at least first and last name to match
            first_name = user_name_parts[0].lower()
            last_name = user_name_parts[-1].lower()
            
            # Check if both first and last name appear in the text
            first_found = any(first_name in found_name.lower() for found_name in found_names)
            last_found = any(last_name in found_name.lower() for found_name in found_names)
            
            # Also check in the raw text
            first_in_text = first_name in text_clean.lower()
            last_in_text = last_name in text_clean.lower()
            
            name_found = (first_found or first_in_text) and (last_found or last_in_text)
            
            print(f"First name '{first_name}' found: {first_found or first_in_text}")
            print(f"Last name '{last_name}' found: {last_found or last_in_text}")
        
        elif len(user_name_parts) == 1:
            # For single names, check if it appears in document
            single_name = user_name_parts[0].lower()
            name_found = any(single_name in found_name.lower() for found_name in found_names) or single_name in text_clean.lower()
            
            print(f"Single name '{single_name}' found: {name_found}")
        
        print(f"Final verification result: {name_found}")
        
        return {
            'verified': name_found,
            'found_names': found_names[:3]  # Return first 3 names found
        }
        
    except Exception as e:
        print(f"Name verification error: {e}")
        return {
            'verified': False,
            'found_names': []
        }

def clean_name_for_verification(name):
    """Clean and normalize name for strict comparison"""
    if not name:
        return ""
    
    # Remove extra spaces, special characters, keep only letters and spaces
    cleaned = re.sub(r'[^a-zA-Z\s]', '', name)
    cleaned = ' '.join(cleaned.split())  # Remove extra spaces
    return cleaned

def classify_document_by_content(text, filename):
    """Classify document based on extracted text content"""
    
    if any(keyword in text for keyword in ['identity number', 'id number', 'south african', 'republic of south africa']):
        return {
            'detected_type': 'South African Identity Document',
            'confidence': 95,
            'details': '🆔 SA Identity Document detected',
            'status': 'Valid ID document'
        }
    elif any(keyword in text for keyword in ['matric', 'grade 12', 'senior certificate', 'national senior certificate']):
        return {
            'detected_type': 'Matric Certificate (Grade 12)',
            'confidence': 90,
            'details': '🎓 Matric Certificate detected',
            'status': 'Academic qualification verified'
        }
    elif any(keyword in text for keyword in ['bank statement', 'account balance', 'transaction', 'deposit']):
        return {
            'detected_type': 'Bank Statement',
            'confidence': 85,
            'details': '🏦 Bank statement detected',
            'status': 'Financial document verified'
        }
    elif any(keyword in text for keyword in ['salary', 'income', 'payslip', 'pay slip']):
        return {
            'detected_type': 'Income Proof / Payslip',
            'confidence': 88,
            'details': '💰 Income proof detected',
            'status': 'Income verification document'
        }
    else:
        return {
            'detected_type': 'Supporting Document',
            'confidence': 60,
            'details': '📄 Document uploaded successfully',
            'status': 'Additional document received'
        }

def store_document_info(user_id, doc_id, document_name, analysis):
    """Store document information in DynamoDB"""
    try:
        try:
            response = applications_table.get_item(Key={'user_id': user_id})
            user_data = response.get('Item', {})
        except:
            user_data = {}
        
        if 'documents' not in user_data:
            user_data['documents'] = []
        
        document_info = {
            'doc_id': doc_id,
            'name': document_name,
            'detected_type': analysis['detected_type'],
            'confidence': analysis['confidence'],
            'details': analysis['details'],
            'status': analysis['status'],
            'uploaded_at': datetime.now().isoformat(),
            'verified': analysis['confidence'] > 70,
            'source': 'whatsapp'
        }
        
        user_data['documents'].append(document_info)
        user_data['user_id'] = user_id
        user_data['last_updated'] = datetime.now().isoformat()
        
        applications_table.put_item(Item=user_data)
        
    except Exception as e:
        print(f"Storage error: {e}")

def is_status_request(message):
    """Check if message is asking for application status"""
    status_keywords = [
        'application status', 'check status', 'my status', 'status check',
        'application progress', 'check application', 'my application',
        'where is my application', 'application update'
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in status_keywords)

def handle_status_request(message):
    """Handle application status requests for WhatsApp"""
    return """📋 *Application Status Check*

Please provide your Student ID to check your application status.

Example: DEMO001

Our demo Student IDs:
• DEMO001 (John Student)
• DEMO002 (Sarah Wilson)  
• STU2025001 (Mike Johnson)"""

def handle_student_id_lookup(student_id):
    """Look up application status by student ID"""
    user_name, app_data = get_application_by_student_id(student_id.upper())
    
    if user_name and app_data:
        return format_status_for_whatsapp(user_name)
    else:
        return f"No application found for Student ID: {student_id}. Please check your ID and try again."
