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
            
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'text/xml'},
                'body': twiml_response
            }
        
        # Handle GET requests (webhook verification)
        elif event['httpMethod'] == 'GET':
            return {
                'statusCode': 200,
                'body': 'WhatsApp webhook is active'
            }
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
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
    """Only use Bedrock for FallbackIntent or very low confidence"""
    
    # Check Lex confidence and intent
    if 'interpretations' in lex_response and lex_response['interpretations']:
        intent_name = lex_response['interpretations'][0].get('intent', {}).get('name', '')
        confidence = lex_response['interpretations'][0].get('nluConfidence', {}).get('score', 0)
        
        # Only use Bedrock for explicit fallback or very low confidence
        if intent_name == 'FallbackIntent' or confidence < 0.3:
            return True
    
    return False

def handle_with_bedrock(user_input):
    """Simple Bedrock handling"""
    try:
        prompt = f"""You are EduBot, a university assistant. Answer briefly for WhatsApp: "{user_input}"

Keep responses under 100 words. Focus on:
- EduBot University programs
- Application process
- Document requirements
- Fees and aid

Be direct and helpful."""

        response = bedrock.invoke_model(
            modelId='anthropic.claude-3-haiku-20240307-v1:0',
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 150,
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        
        result = json.loads(response['body'].read())
        bedrock_response = result['content'][0]['text']
        
        return clean_bedrock_response(bedrock_response)
        
    except Exception as e:
        print(f"Bedrock error: {e}")
        return "I can help you with EduBot University applications and course information. What would you like to know?"

def clean_bedrock_response(response):
    """Clean up Bedrock response for WhatsApp"""
    # Remove any problematic characters
    cleaned = response.replace('*', '').replace('_', '').strip()
    return cleaned[:500]  # Limit length for WhatsApp

def format_for_whatsapp(text):
    """Format text for WhatsApp"""
    return text.replace('*', '').replace('_', '').strip()[:500]

def is_status_request(message):
    """Check if message is asking for application status"""
    status_keywords = [
        'application status', 'check status', 'my status', 'status check',
        'application progress', 'check application', 'my application'
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in status_keywords)

def handle_status_request(message):
    """Handle status request - ask for student ID"""
    return "Please provide your Student ID to check your application status (e.g., DEMO001, STU2025001)"

def handle_student_id_lookup(student_id):
    """Look up application status by student ID"""
    try:
        user_name, app_data = get_application_by_student_id(student_id.upper())
        if app_data:
            return format_status_for_whatsapp(user_name)
        else:
            return f"No application found for Student ID: {student_id}. Please check your ID or contact admissions."
    except Exception as e:
        print(f"Status lookup error: {e}")
        return "Sorry, I couldn't retrieve your status right now. Please try again later."

def handle_document_upload(parsed_data, from_number):
    """Handle document upload from WhatsApp"""
    try:
        # Get media URL
        media_url = parsed_data.get('MediaUrl0', [''])[0]
        media_content_type = parsed_data.get('MediaContentType0', [''])[0]
        
        if not media_url:
            return "No document received. Please try uploading again."
        
        # Download and process document
        file_data = download_media_from_twilio(media_url)
        if not file_data:
            return "Sorry, I couldn't download your document. Please try again."
        
        # Simple response for now
        return "Document received! For full verification, please use our web portal or provide your Student ID for status updates."
        
    except Exception as e:
        print(f"Document upload error: {e}")
        return "Sorry, there was an error processing your document. Please try again."

def download_media_from_twilio(media_url):
    """Download media file from Twilio with authentication"""
    try:
        # Check if auth token is configured
        if TWILIO_AUTH_TOKEN == 'your_auth_token_here':
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
