# Deployment Guide

## Prerequisites
- AWS Account with appropriate permissions
- AWS CLI configured
- Python 3.9+

## AWS Services Required
- Lambda Functions (3)
- DynamoDB Tables (2)
- S3 Bucket
- API Gateway
- AWS Lex
- Amazon Bedrock
- AWS Textract

## Quick Deploy Steps

1. **Create DynamoDB Tables**
   ```bash
   aws dynamodb create-table --table-name edubot-users --attribute-definitions AttributeName=student_id,AttributeType=S --key-schema AttributeName=student_id,KeyType=HASH --billing-mode PAY_PER_REQUEST

   aws dynamodb create-table --table-name whatsapp-loan-demo-applications --attribute-definitions AttributeName=user_name,AttributeType=S --key-schema AttributeName=user_name,KeyType=HASH --billing-mode PAY_PER_REQUEST
   ```

2. **Deploy Lambda Functions**
   - `registration-bot/frontend/edubot_fixed.py` → `whatsapp-loan-demo-login`
   - `registration-bot/lambda/chat_lex_bedrock_handler.py` → `whatsapp-loan-demo-lex-chat`
   - `registration-bot/lambda/edubot_whatsapp_simple.py` → `edubot-whatsapp-handler`
   - `registration-bot/lambda/textract_name_verification_handler.py` → `textract-name-verification`

3. **Configure Environment Variables**
   - Set up AWS service permissions
   - Configure Lex Bot ARN
   - Set Bedrock model access
   - Configure S3 bucket names

4. **Set up API Gateway**
   - Create REST API
   - Configure CORS
   - Set up Lambda integrations

## Environment Variables
```
LEX_BOT_ID=your-lex-bot-id
LEX_BOT_ALIAS_ID=your-alias-id
BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
S3_BUCKET_NAME=your-document-bucket
```


