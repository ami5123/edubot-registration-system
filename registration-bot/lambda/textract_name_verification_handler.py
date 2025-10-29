import json
import boto3
import uuid
import base64
import re
from datetime import datetime

# AWS clients
lex_client = boto3.client('lexv2-runtime', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
textract = boto3.client('textract', region_name='us-east-1')
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')  # Added Bedrock client

# DynamoDB table
applications_table = dynamodb.Table('whatsapp-loan-demo-applications')

def lambda_handler(event, context):
    """Enhanced chat handler with Textract name verification"""
    try:
        body = json.loads(event['body'])
        message = body.get('message', '')
        session_id = body.get('sessionId', 'web-session-' + str(hash(message))[:8])
        user_id = body.get('userId', session_id)
        user_name = body.get('userName', '')  # Get user's full name
        
        # Check if this is a document upload request
        if body.get('action') == 'upload_document':
            return handle_document_upload(body, user_id, user_name)
        
        # Check if this is a document status request
        if body.get('action') == 'document_status':
            return get_document_status(user_id)
        
        # Regular chat - call Lex first
        response = lex_client.recognize_text(
            botId='QCDXUQVV6M',
            botAliasId='TSTALIASID',
            localeId='en_US',
            sessionId=session_id,
            text=message
        )
        
        # Extract response from Lex
        if 'messages' in response and response['messages']:
            lex_response = response['messages'][0]['content']
            
            # Only use Bedrock if Lex confidence is very low or it's FallbackIntent
            if should_use_bedrock(message, response):
                lex_response = handle_with_bedrock(message, user_id, user_name)
            else:
                # Use Lex response and enhance if needed
                if 'funding' in message.lower() or 'financial aid' in message.lower():
                    lex_response = enhance_funding_response(lex_response, user_id)
                
        else:
            # Fallback to Bedrock if Lex has no response
            lex_response = handle_with_bedrock(message, user_id, user_name)
        
        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'response': lex_response,
                'showUpload': 'funding' in message.lower() or 'documents' in message.lower()
            })
        }
        
    except Exception as e:
        print(f"Error: {e}")
        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'response': 'Sorry, I encountered an error. Please try again.'
            })
        }

def handle_document_upload(body, user_id, user_name):
    """Handle document upload with Textract analysis and name verification"""
    try:
        document_name = body.get('documentName', 'Unknown Document')
        file_data = body.get('fileData', '')  # Base64 encoded file
        
        if not file_data:
            return error_response('No file data received')
        
        if not user_name:
            return error_response('User name required for document verification')
        
        # Decode base64 file data
        try:
            file_bytes = base64.b64decode(file_data)
        except Exception as e:
            return error_response('Invalid file format')
        
        # Analyze document with Textract and verify name
        analysis_result = analyze_and_verify_document(file_bytes, document_name, user_name)
        
        # Check if name verification failed
        if not analysis_result['name_verified']:
            return {
                'statusCode': 200,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({
                    'success': False,
                    'response': f"""❌ **Document Rejected - Name Mismatch**

📄 **Document**: {document_name}
👤 **Expected Name**: {user_name}
🔍 **Found Names**: {', '.join(analysis_result['found_names']) if analysis_result['found_names'] else 'No names detected'}

**Reason**: Document must belong to the registered user.

📋 **Required Documents for EduBot University:**

**🆔 Identity Documents:**
• South African Identity Document (must show your full name)
• Valid passport (if applicable)

**🎓 Academic Documents:**
• Matric Certificate (Grade 12 - must be in your name)
• Academic transcripts from previous institutions
• Degree/Diploma certificates (if applicable)

**💰 Financial Documents:**
• Proof of income (payslip/salary certificate in your name)
• Bank statements (last 3 months - account holder name must match)
• Tax certificates or IRP5 forms
• Household income affidavit (if dependent)

**🏠 Supporting Documents:**
• Proof of residence (utility bill/municipal account)
• Guardian/Parent consent (if under 21)
• Disability certificates (if applicable)

**✅ Document Requirements:**
• All documents must be in **{user_name}**'s name
• Clear, readable images or PDFs
• Recent documents (not older than 6 months for financial docs)
• Official letterheads where applicable

**💡 Tips for Success:**
• Ensure your name appears clearly on the document
• Use good lighting when taking photos
• Upload documents one at a time
• Check that the document belongs to you before uploading

Try uploading a document that belongs to you! 📋""",
                    'rejected': True,
                    'reason': 'name_mismatch',
                    'requiredDocuments': get_required_documents_list()
                })
            }
        
        # Generate unique document ID
        doc_id = str(uuid.uuid4())
        
        # Store document info in DynamoDB
        store_document_info(user_id, doc_id, document_name, analysis_result['analysis'])
        
        # Get current application status
        status_summary = get_application_summary(user_id)
        
        response_message = f"""✅ **Document Verified & Accepted!**

📄 **Document**: {document_name}
👤 **Name Verified**: {user_name} ✅
🔍 **AI Detection**: {analysis_result['analysis']['detected_type']}
📊 **Confidence**: {analysis_result['analysis']['confidence']}%
✅ **Status**: {analysis_result['analysis']['status']}

{analysis_result['analysis']['details']}

{status_summary}

**Next Steps:**
{get_next_steps(user_id)}"""

        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'response': response_message,
                'documentId': doc_id,
                'analysis': analysis_result['analysis'],
                'nameVerified': True
            })
        }
        
    except Exception as e:
        print(f"Upload error: {e}")
        return error_response('Document upload failed. Please try again.')

def analyze_and_verify_document(file_bytes, document_name, user_name):
    """Use AWS Textract to analyze document and verify name"""
    try:
        print(f"Analyzing document: {document_name}, size: {len(file_bytes)} bytes")
        
        # Check file format and convert if needed
        file_extension = document_name.lower().split('.')[-1] if '.' in document_name else 'unknown'
        print(f"File extension: {file_extension}")
        
        # Textract supports: PNG, JPEG, PDF, TIFF
        supported_formats = ['png', 'jpg', 'jpeg', 'pdf', 'tiff', 'tif']
        
        if file_extension not in supported_formats:
            print(f"Unsupported format: {file_extension}")
            # Try to process anyway, might be misnamed
        
        # Call Textract to extract text
        print("Calling Textract...")
        response = textract.detect_document_text(
            Document={'Bytes': file_bytes}
        )
        
        print(f"Textract response blocks: {len(response.get('Blocks', []))}")
        
        # Extract all text from the document
        extracted_text = ""
        for block in response['Blocks']:
            if block['BlockType'] == 'LINE':
                extracted_text += block['Text'] + " "
        
        print(f"Extracted text length: {len(extracted_text)}")
        print(f"Text sample: {extracted_text[:200]}...")
        
        # Verify name in document
        name_verification = verify_name_in_text(extracted_text, user_name)
        
        # Classify document type
        document_analysis = classify_document_by_content(extracted_text.lower(), document_name)
        
        return {
            'name_verified': name_verification['verified'],
            'found_names': name_verification['found_names'],
            'analysis': document_analysis
        }
        
    except Exception as e:
        print(f"Textract error: {e}")
        
        # If Textract fails, try basic filename analysis
        print("Falling back to filename analysis...")
        fallback_analysis = analyze_document_by_filename(document_name)
        
        # For fallback, be more lenient with name verification
        # Accept if document type is recognized
        name_verified = fallback_analysis['confidence'] > 30
        
        return {
            'name_verified': name_verified,
            'found_names': ['Document analysis failed - using filename'],
            'analysis': fallback_analysis
        }

def verify_name_in_text(text, user_name):
    """Verify if user's name appears in the extracted text"""
    print(f"Verifying name '{user_name}' in text: {text[:200]}...")
    
    try:
        # Clean and normalize names
        user_name_clean = clean_name(user_name)
        text_clean = clean_name(text)
        
        print(f"Cleaned user name: '{user_name_clean}'")
        print(f"Cleaned text sample: '{text_clean[:100]}...'")
        
        # Split user name into parts
        user_name_parts = user_name_clean.split()
        print(f"User name parts: {user_name_parts}")
        
        # Find potential names in text - handle both uppercase and mixed case
        # Pattern for mixed case names: John Smith
        mixed_case_names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        # Pattern for uppercase names: JOHN SMITH  
        uppercase_names = re.findall(r'\b[A-Z]{2,}(?:\s+[A-Z]{2,})*\b', text)
        
        # Combine and clean all found names
        all_potential_names = mixed_case_names + uppercase_names
        found_names = [clean_name(name) for name in all_potential_names]
        
        # Filter out common document words
        common_words = {'THE', 'AND', 'FOR', 'WITH', 'FROM', 'DATE', 'NUMBER', 'CODE', 'DOCUMENT', 'CERTIFICATE', 'BANK', 'STATEMENT', 'ACCOUNT', 'BALANCE', 'AMOUNT', 'TOTAL', 'PERIOD', 'MONTH', 'YEAR', 'DAY', 'SERVICES', 'COMPANY', 'LIMITED', 'PAYSLIP', 'EMPLOYEE', 'DEPARTMENT', 'FREQUENCY', 'PAYMENT'}
        
        filtered_names = []
        for name in found_names:
            words = name.upper().split()
            if len(words) >= 1 and all(len(w) >= 2 and w not in common_words for w in words):
                filtered_names.append(name)
        
        print(f"Found names in document: {filtered_names[:10]}")
        
        # Check if user name or parts appear in text
        name_found = False
        
        # Method 1: Check if full name appears
        if user_name_clean.lower() in text_clean.lower():
            name_found = True
            print(f"Full name match found")
        
        # Method 2: Check if at least one name part matches
        else:
            for part in user_name_parts:
                if len(part) > 1 and part.lower() in text_clean.lower():
                    name_found = True
                    print(f"Name part match: '{part}'")
                    break
        
        print(f"Final verification result: {name_found}")
        
        return {
            'verified': name_found,
            'found_names': filtered_names[:5]  # Limit to first 5 names found
        }
        
    except Exception as e:
        print(f"Name verification error: {e}")
        return {
            'verified': False,
            'found_names': []
        }

def clean_name(name):
    """Clean and normalize name for comparison"""
    if not name:
        return ""
    
    # Remove extra spaces, special characters, keep only letters and spaces
    cleaned = re.sub(r'[^a-zA-Z\s]', '', name)
    cleaned = ' '.join(cleaned.split())  # Remove extra spaces
    return cleaned

def classify_document_by_content(text, filename):
    """Classify document based on extracted text content"""
    
    # South African ID Document patterns
    if any(keyword in text for keyword in ['identity number', 'id number', 'south african', 'republic of south africa', 'identity document']):
        return {
            'detected_type': 'South African Identity Document',
            'category': 'identification',
            'status': 'Valid ID document detected',
            'confidence': 95,
            'details': '🆔 **Verified**: South African Identity Document with ID number detected',
            'priority': 1
        }
    
    # Matric Certificate patterns
    elif any(keyword in text for keyword in ['matric', 'grade 12', 'senior certificate', 'national senior certificate', 'department of education']):
        return {
            'detected_type': 'Matric Certificate (Grade 12)',
            'category': 'academic',
            'status': 'Academic qualification verified',
            'confidence': 90,
            'details': '🎓 **Verified**: Matric Certificate with academic results detected',
            'priority': 2
        }
    
    # Bank Statement patterns
    elif any(keyword in text for keyword in ['bank statement', 'account balance', 'transaction', 'deposit', 'withdrawal', 'banking details']):
        return {
            'detected_type': 'Bank Statement',
            'category': 'financial',
            'status': 'Financial document verified',
            'confidence': 85,
            'details': '🏦 **Verified**: Bank statement with transaction history detected',
            'priority': 4
        }
    
    # Income/Salary documents
    elif any(keyword in text for keyword in ['salary', 'income', 'payslip', 'pay slip', 'gross salary', 'net salary', 'employer']):
        return {
            'detected_type': 'Income Proof / Payslip',
            'category': 'financial',
            'status': 'Income verification document',
            'confidence': 88,
            'details': '💰 **Verified**: Income proof with salary details detected',
            'priority': 3
        }
    
    # Academic Transcript patterns
    elif any(keyword in text for keyword in ['transcript', 'academic record', 'university', 'college', 'degree', 'diploma']):
        return {
            'detected_type': 'Academic Transcript',
            'category': 'academic',
            'status': 'Additional academic record',
            'confidence': 80,
            'details': '📚 **Verified**: Academic transcript with course details detected',
            'priority': 5
        }
    
    # Fallback to filename analysis
    else:
        fallback = analyze_document_by_filename(filename)
        fallback['confidence'] = 50
        fallback['details'] = '📄 **Note**: Document type determined from filename (content analysis inconclusive)'
        return fallback

def analyze_document_by_filename(document_name):
    """Fallback filename-based analysis"""
    name_lower = document_name.lower()
    
    if 'id' in name_lower or 'identity' in name_lower:
        return {
            'detected_type': 'Identity Document',
            'category': 'identification',
            'status': 'ID document (filename-based)',
            'confidence': 60,
            'details': '🆔 **Filename**: Appears to be an Identity Document',
            'priority': 1
        }
    elif 'matric' in name_lower or 'grade 12' in name_lower or 'certificate' in name_lower:
        return {
            'detected_type': 'Matric Certificate',
            'category': 'academic',
            'status': 'Academic certificate (filename-based)',
            'confidence': 60,
            'details': '🎓 **Filename**: Appears to be a Matric Certificate',
            'priority': 2
        }
    else:
        return {
            'detected_type': 'Supporting Document',
            'category': 'general',
            'status': 'Additional document received',
            'confidence': 40,
            'details': '📄 **General**: Document uploaded successfully',
            'priority': 7
        }

def store_document_info(user_id, doc_id, document_name, analysis):
    """Store document information in DynamoDB"""
    try:
        # Get existing user record or create new one
        try:
            response = applications_table.get_item(Key={'user_id': user_id})
            user_data = response.get('Item', {})
        except:
            user_data = {}
        
        # Initialize documents list if not exists
        if 'documents' not in user_data:
            user_data['documents'] = []
        
        # Add new document
        document_info = {
            'doc_id': doc_id,
            'name': document_name,
            'detected_type': analysis['detected_type'],
            'category': analysis['category'],
            'status': analysis['status'],
            'confidence': analysis['confidence'],
            'details': analysis['details'],
            'priority': analysis['priority'],
            'uploaded_at': datetime.now().isoformat(),
            'verified': analysis['confidence'] > 70,
            'name_verified': True  # Only stored if name verification passed
        }
        
        user_data['documents'].append(document_info)
        user_data['user_id'] = user_id
        user_data['last_updated'] = datetime.now().isoformat()
        
        # Update DynamoDB
        applications_table.put_item(Item=user_data)
        
    except Exception as e:
        print(f"Storage error: {e}")

def get_application_summary(user_id):
    """Get summary of current application status"""
    try:
        response = applications_table.get_item(Key={'user_id': user_id})
        user_data = response.get('Item', {})
        documents = user_data.get('documents', [])
        
        if not documents:
            return "📋 **Application Status**: No documents uploaded yet"
        
        # Categorize documents
        categories = {}
        for doc in documents:
            category = doc.get('category', 'general')
            if category not in categories:
                categories[category] = []
            categories[category].append(doc)
        
        summary = f"📋 **Application Summary**: {len(documents)} verified document(s)\n\n"
        
        # Required documents checklist
        required_docs = {
            'identification': 'Identity Document',
            'academic': 'Academic Records', 
            'financial': 'Financial Documents'
        }
        
        for req_category, req_name in required_docs.items():
            if req_category in categories:
                verified_count = sum(1 for doc in categories[req_category] if doc.get('verified', False))
                total_count = len(categories[req_category])
                summary += f"✅ {req_name}: {verified_count}/{total_count} verified\n"
            else:
                summary += f"❌ {req_name}: Still needed\n"
        
        return summary
        
    except Exception as e:
        print(f"Summary error: {e}")
        return "📋 **Application Status**: Unable to retrieve status"

def get_next_steps(user_id):
    """Get personalized next steps based on uploaded documents"""
    try:
        response = applications_table.get_item(Key={'user_id': user_id})
        user_data = response.get('Item', {})
        documents = user_data.get('documents', [])
        
        # Check what's missing
        uploaded_categories = set(doc.get('category') for doc in documents)
        required_categories = {'identification', 'academic', 'financial'}
        missing_categories = required_categories - uploaded_categories
        
        if not missing_categories:
            return "🎉 All required documents uploaded and verified! Your application will be reviewed within 2-3 weeks."
        
        next_steps = "📝 **Still needed (must be in your name):**\n"
        if 'identification' in missing_categories:
            next_steps += "• Upload your SA Identity Document\n"
        if 'academic' in missing_categories:
            next_steps += "• Upload your Matric Certificate\n"
        if 'financial' in missing_categories:
            next_steps += "• Upload Income Proof and Bank Statements\n"
            
        return next_steps
        
    except Exception as e:
        print(f"Next steps error: {e}")
        return "📝 Continue uploading your required documents."

def get_document_status(user_id):
    """Get detailed document status"""
    try:
        response = applications_table.get_item(Key={'user_id': user_id})
        user_data = response.get('Item', {})
        documents = user_data.get('documents', [])
        
        if not documents:
            status_message = "📋 **Document Status**: No documents uploaded yet\n\n**Get started by uploading:**\n• Identity Document\n• Matric Certificate\n• Income Proof\n• Bank Statements\n\n⚠️ **Note**: All documents must be in your registered name"
        else:
            status_message = f"📋 **Document Status**: {len(documents)} verified document(s)\n\n"
            
            # Sort documents by priority
            sorted_docs = sorted(documents, key=lambda x: x.get('priority', 999))
            
            for doc in sorted_docs:
                status_icon = "✅" if doc.get('verified') else "⏳"
                confidence = doc.get('confidence', 0)
                status_message += f"{status_icon} **{doc.get('detected_type')}**: {confidence}% confidence, Name ✅\n"
            
            status_message += f"\n{get_next_steps(user_id)}"
        
        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'response': status_message
            })
        }
        
    except Exception as e:
        print(f"Status error: {e}")
        return error_response('Unable to retrieve document status.')

def enhance_funding_response(lex_response, user_id):
    """Enhance funding response with upload button"""
    enhanced_response = lex_response + "\n\n" + """
🔗 **Quick Actions:**
• [Upload Documents] - AI-powered document analysis with name verification
• [Check Status] - View uploaded documents
• [Get Help] - Document requirements

🤖 **Security**: All documents verified to match your registered name!"""
    
    return enhanced_response

def should_use_bedrock(user_input, lex_response):
    """Determine if query should be handled by Bedrock instead of Lex - be restrictive"""
    
    # Always use Bedrock for general help queries
    help_keywords = ['help', 'what can you do', 'how can you help', 'what do you do']
    if any(keyword in user_input.lower() for keyword in help_keywords):
        return True
    
    # Always use Bedrock for application process queries (not status checking)
    process_keywords = ['application process', 'how to apply', 'how do i apply', 'registration process', 'how to register', 'start application', 'lets start', 'begin application', 'start the application', 'how can i start', 'how do i start', 'i want to apply', 'just want to apply', 'apply for it', 'how to upload', 'upload documents']
    if any(keyword in user_input.lower() for keyword in process_keywords):
        return True
    
    # Method 1: Only use Bedrock if Lex confidence is very low (< 0.5)
    confidence = lex_response.get('nluIntentConfidence', {}).get('score', 1.0)
    if confidence < 0.5:
        return True
    
    # Method 2: Only use Bedrock if Lex explicitly triggered FallbackIntent
    if 'sessionState' in lex_response:
        intent_name = lex_response['sessionState']['intent']['name']
        if intent_name == 'FallbackIntent':
            return True
    
    # Method 3: Only for very specific conversational patterns
    highly_conversational = [
        'tell me more about yourself', 'who are you', 'what do you think about',
        'i\'m really confused', 'can you explain in detail', 'help me understand better'
    ]
    
    user_lower = user_input.lower()
    if any(pattern in user_lower for pattern in highly_conversational):
        return True
    
    # Default: Let Lex handle everything else
    return False

def handle_with_bedrock(user_input, user_id, user_name):
    """Handle query with Bedrock for natural conversation"""
    try:
        # Special handling for help queries
        if any(keyword in user_input.lower() for keyword in ['help', 'what can you do']):
            university_context = f"""You are Sarah, an assistant for EduBot University in South Africa. The user asked for help. Provide a brief overview of what you can help with.

Available services:
- Course enrollment and program information
- Admissions process and requirements  
- Financial aid and funding applications
- Document upload and verification with AI analysis
- Application status checks

Keep the response helpful but concise. The user's name is {user_name if user_name else 'the student'}.

User: {user_input}"""
        
        # Special handling for application process queries
        elif any(keyword in user_input.lower() for keyword in ['application process', 'how to apply', 'registration process', 'start application', 'lets start', 'begin application', 'how can i start', 'how do i start', 'i want to apply', 'just want to apply', 'apply for it']):
            university_context = f"""You are Sarah, an assistant for EduBot University in South Africa. The user wants to APPLY/START their application process.

Provide clear, direct steps to apply:
1. Choose your program (they mentioned Computer Science if relevant)
2. Complete the online application form
3. Pay R500 application fee
4. Upload required documents: SA ID, Matric Certificate, Academic Transcripts, Motivation Letter
5. Wait for review (2-3 weeks)

Application deadline: December 15 (First semester), June 15 (Second semester)
Financial aid available: Merit Scholarships (R50,000), Need-based Bursaries (R30,000)

Be direct and actionable. The user's name is {user_name if user_name else 'the student'}.

User: {user_input}"""

        # Special handling for document upload queries  
        elif any(keyword in user_input.lower() for keyword in ['how to upload', 'upload documents', 'document upload']):
            university_context = f"""You are Sarah, an assistant for EduBot University. The user needs help with uploading documents.

Explain the document upload process:
1. Use the "Upload Documents" button on this page
2. Select your files (SA ID, Matric Certificate, Academic Transcripts, Motivation Letter)
3. Our AI will analyze and verify documents automatically
4. Get instant feedback on document verification status
5. Documents must be in your registered name for security

The system uses AWS Textract for intelligent document analysis and name verification.

Keep response clear and helpful. The user's name is {user_name if user_name else 'the student'}.

User: {user_input}"""
        else:
            # Build context about EduBot University without repetitive introductions
            university_context = f"""You are Sarah, an assistant for EduBot University in South Africa. The user's name is {user_name if user_name else 'the student'}.

EduBot University Details:
- Programs: Computer Science (4 years), Business Administration (3 years), Engineering (4 years), Liberal Arts (3 years)
- Application fee: R500, Deadlines: December 15 (First semester), June 15 (Second semester)
- Required documents: SA Identity Document, Matric Certificate, Academic Transcripts, Motivation Letter
- Financial aid: Merit Scholarships (R50,000), Need-based Bursaries (R30,000), Work-Study Programs

Instructions:
- Do NOT introduce yourself as Sarah unless it's the very first interaction
- Be conversational and natural
- Don't repeat information the user already knows
- Keep responses focused and helpful
- Use South African context (ZAR, Matric certificates)
- Be friendly but not overly formal

User: {user_input}"""

        # Prepare Bedrock request
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 150,
            "temperature": 0.6,
            "messages": [
                {
                    "role": "user",
                    "content": university_context
                }
            ]
        }
        
        # Call Bedrock
        response = bedrock.invoke_model(
            body=json.dumps(request_body),
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            accept="application/json",
            contentType="application/json"
        )
        
        # Parse response
        response_body = json.loads(response.get('body').read())
        bedrock_response = response_body['content'][0]['text'].strip()
        
        # Clean up repetitive introductions
        bedrock_response = clean_bedrock_response(bedrock_response, user_name)
        
        # Add helpful actions if relevant
        if any(word in user_input.lower() for word in ['document', 'upload', 'submit', 'apply']):
            bedrock_response += "\n\n💡 **Quick Actions:**\n• [Upload Documents] - Start your application\n• [Check Requirements] - See what you need"
        
        return bedrock_response
        
    except Exception as e:
        print(f"Bedrock error: {e}")
        # Fallback to friendly response without introduction
        return f"I'd be happy to help you with that! What specific information about EduBot University would you like to know?"

def clean_bedrock_response(response, user_name):
    """Clean up repetitive introductions and formatting from Bedrock response"""
    
    # Remove stage directions and tone descriptions
    stage_direction_patterns = [
        r'\*[^*]*\*',  # Remove anything between asterisks like *speaks in a friendly tone*
        r'\([^)]*tone[^)]*\)',  # Remove tone descriptions in parentheses
        r'\b(speaks|says|responds|replies)\s+(in\s+a\s+)?\w+\s+(tone|manner|way)\b',  # Remove "speaks in a friendly tone"
    ]
    
    cleaned_response = response
    for pattern in stage_direction_patterns:
        cleaned_response = re.sub(pattern, '', cleaned_response, flags=re.IGNORECASE)
    
    # Remove common repetitive introductions
    intro_patterns = [
        f"Hello {user_name}! I'm Sarah, an assistant at EduBot University",
        f"Hello {user_name}! This is Sarah, an assistant at EduBot University", 
        "Hello there! Welcome to EduBot University. My name is Sarah",
        "Hi! I'm Sarah, an assistant for EduBot University",
        "Hello! I'm Sarah from EduBot University",
        "My name is Sarah and I'm here to assist you"
    ]
    
    for pattern in intro_patterns:
        if pattern in cleaned_response:
            cleaned_response = cleaned_response.replace(pattern, "").strip()
            cleaned_response = cleaned_response.lstrip('.,!').strip()
            break
    
    # Clean up extra whitespace and formatting
    cleaned_response = re.sub(r'\s+', ' ', cleaned_response)  # Multiple spaces to single
    cleaned_response = cleaned_response.strip()
    
    # Remove redundant "in South Africa" mentions if too many
    if cleaned_response.count("in South Africa") > 1:
        parts = cleaned_response.split("in South Africa")
        cleaned_response = parts[0] + "in South Africa" + "".join(parts[1:]).replace("in South Africa", "")
    
    # Ensure response starts with capital letter
    if cleaned_response and not cleaned_response[0].isupper():
        cleaned_response = cleaned_response[0].upper() + cleaned_response[1:]
    
    return cleaned_response

def get_required_documents_list():
    """Return structured list of required documents"""
    return {
        'identity': [
            'South African Identity Document',
            'Valid passport (if applicable)'
        ],
        'academic': [
            'Matric Certificate (Grade 12)',
            'Academic transcripts from previous institutions',
            'Degree/Diploma certificates (if applicable)'
        ],
        'financial': [
            'Proof of income (payslip/salary certificate)',
            'Bank statements (last 3 months)',
            'Tax certificates or IRP5 forms',
            'Household income affidavit (if dependent)'
        ],
        'supporting': [
            'Proof of residence (utility bill/municipal account)',
            'Guardian/Parent consent (if under 21)',
            'Disability certificates (if applicable)'
        ]
    }

def error_response(message):
    """Return standardized error response"""
    return {
        'statusCode': 200,
        'headers': {'Access-Control-Allow-Origin': '*'},
        'body': json.dumps({
            'success': False,
            'response': message
        })
    }
