import json
import boto3
import re
import uuid
import base64
from textract_name_verification_handler import analyze_and_verify_document
from application_data import format_status_for_web, update_document_status, classify_document_type

# Initialize AWS clients
lex_client = boto3.client('lexv2-runtime', region_name='us-east-1')
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

def lambda_handler(event, context):
    try:
        # Handle GET requests - redirect to login page
        if event['httpMethod'] == 'GET':
            return {
                'statusCode': 302,
                'headers': {'Location': '/demo/login'},
                'body': ''
            }
        
        # Handle POST requests - process chat messages or file uploads
        if event['httpMethod'] == 'POST':
            body = json.loads(event['body'])
            
            # Check if it's a file upload (has fileData)
            if 'fileData' in body:
                return handle_file_upload(event, context)
            else:
                return handle_text_message(event, context)
        
        # Handle OPTIONS for CORS
        if event['httpMethod'] == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type'
                },
                'body': ''
            }
            
    except Exception as e:
        print(f"Chat error: {e}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'response': 'I can help you with EduBot University. What would you like to know?',
                'success': False,
                'error': str(e)
            })
        }

def handle_text_message(event, context):
    """Handle regular text messages"""
    body = json.loads(event['body'])
    message = body.get('message', '')
    session_id = body.get('sessionId', str(uuid.uuid4()))
    user_name = body.get('userName', '')  # Get user name from request
    
    # Check if user is asking for application status
    if is_status_request(message):
        if user_name:
            response_text = format_status_for_web(user_name)
        else:
            response_text = "Please log in to check your application status."
    else:
        # Process with Lex + Bedrock hybrid AI
        response_text = process_with_hybrid_ai(message, session_id)
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type'
        },
        'body': json.dumps({
            'response': response_text,
            'success': True
        })
    }

def is_status_request(message):
    """Check if message is asking for application status"""
    status_keywords = [
        'application status', 'check status', 'my status', 'status check',
        'application progress', 'check application', 'my application',
        'where is my application', 'application update'
    ]
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in status_keywords)

def handle_file_upload(event, context):
    """Handle file upload and document processing with real Textract verification"""
    try:
        body = json.loads(event.get('body', '{}'))
        file_data = body.get('fileData')
        file_name = body.get('fileName', 'document')
        user_name = body.get('userName', '')
        message = body.get('message', '')
        
        if not file_data or not user_name:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'response': 'Please provide both file data and user name for verification.',
                    'success': False
                })
            }
        
        # Decode base64 file data
        import base64
        file_bytes = base64.b64decode(file_data)
        
        # Process with Textract
        result = analyze_and_verify_document(file_bytes, file_name, user_name)
        
        # Update application status based on verification result
        document_type = classify_document_type(file_name, result)
        update_success = update_document_status(user_name, document_type, result)
        
        # Format response based on verification result
        if result['name_verified']:
            response_text = f"""✅ **Document Verified Successfully!**

📄 **File**: {file_name}
👤 **User**: {user_name}
✅ **Name Match**: Verified
📋 **Document Type**: {document_type}

**Found Names**: {', '.join(result['found_names'])}

Your {document_type.lower()} has been successfully verified and your application status has been updated! Check your application status to see the progress."""
        else:
            response_text = f"""❌ **Document Verification Failed**

📄 **File**: {file_name}
👤 **Expected**: {user_name}
❌ **Name Match**: Not found
📋 **Document Type**: {document_type}

**Found Names**: {', '.join(result['found_names']) if result['found_names'] else 'None detected'}

The document could not be verified. Please ensure:
• The document contains your full name
• The image/PDF is clear and readable
• Your name matches your profile exactly

Your application status has been updated to reflect this verification attempt."""
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            },
            'body': json.dumps({
                'response': response_text,
                'success': True
            })
        }
        
    except Exception as e:
        print(f"File upload error: {e}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'response': f'Sorry, there was an error processing your document: {str(e)}',
                'success': False,
                'error': str(e)
            })
        }

def process_with_hybrid_ai(message, session_id):
    """Process with hybrid Lex + Bedrock - same logic as WhatsApp"""
    try:
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
                return format_for_web(lex_response)
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

def handle_with_bedrock(message):
    """Handle with Bedrock for conversational responses"""
    try:
        prompt = f"""You are EduBot, a concise university assistant. Answer briefly: "{message}"

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
        
        # Clean up any stage directions or repetitive content
        return clean_bedrock_response(bedrock_response)
        
    except Exception as e:
        print(f"Bedrock error: {e}")
        return "I can help you with EduBot University applications and course information. What would you like to know?"

def clean_bedrock_response(response):
    """Clean up Bedrock response"""
    # Remove stage directions like *speaks in friendly tone*
    cleaned = re.sub(r'\*[^*]*\*', '', response)
    
    # Remove repetitive introductions
    if cleaned.lower().startswith(('hello', 'hi there', 'greetings')):
        sentences = cleaned.split('.')
        if len(sentences) > 1:
            cleaned = '.'.join(sentences[1:]).strip()
    
    return cleaned.strip()

def format_for_web(response):
    """Format response for web chat"""
    # Keep response concise for web
    if len(response) > 400:
        response = response[:397] + "..."
    
    return response
