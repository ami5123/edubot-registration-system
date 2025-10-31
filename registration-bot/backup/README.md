# EduBot University - Backup Files

This folder contains backup copies of all EduBot University files.

## Local Development Files (Original)
- `index.html` - Basic EduBot homepage
- `styles.css` - Basic styling
- `script.js` - Basic JavaScript (updated to use API Gateway)
- `server.js` - Node.js local server (localhost:8080)
- `package.json` - Node.js dependencies

## AWS Lambda Deployment Files
- `edubot_fixed.py` - **CURRENT DEPLOYED VERSION** (Complete EduBot with embedded CSS/JS)
- `edubot_complete.py` - Previous version (had CSS loading issues)
- `edubot_frontend.py` - First deployment attempt

## Current Live System
- **URL:** [Deployed on AWS API Gateway]
- **Lambda Function:** whatsapp-loan-demo-login
- **Handler:** edubot_fixed.lambda_handler
- **Features:** Login/Register + Protected Chatbot + Lex Integration

## Demo Accounts
- DEMO001 / demo123 (John Student)
- DEMO002 / password (Sarah Wilson)
- STU2025001 / student123 (Mike Johnson)

## Notes
- Local server no longer needed - everything runs on AWS
- Chat API: [AWS API Gateway Endpoint]
- All CSS/JS embedded in Lambda for reliability
