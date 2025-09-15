from flask import Flask, request, jsonify
from flask_cors import CORS # Keep this line
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import base64
import mailchimp_marketing as MailchimpClient
from dotenv import load_dotenv # Import load_dotenv
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": ["https://hcopreliminary.netlify.app", "http://localhost:3000"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# --- Configuration (Pulled from environment variables) ---
MAILCHIMP_API_KEY = os.environ.get('MAILCHIMP_API_KEY')
MAILCHIMP_SERVER_PREFIX = os.environ.get('MAILCHIMP_SERVER_PREFIX')
MAILCHIMP_AUDIENCE_ID = os.environ.get('MAILCHIMP_AUDIENCE_ID')

EMAIL_HOST = os.environ.get('EMAIL_HOST')
EMAIL_PORT = os.environ.get('EMAIL_PORT', 587)
EMAIL_USERNAME = os.environ.get('EMAIL_USERNAME')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
COMPANY_BCC_EMAIL = os.environ.get('COMPANY_BCC_EMAIL')

# Initialize Mailchimp client
mailchimp = MailchimpClient.Client()
mailchimp.set_config({
    "api_key": MAILCHIMP_API_KEY,
    "server": MAILCHIMP_SERVER_PREFIX
})


@app.route('/', methods=['GET', 'POST', 'OPTIONS'])
def root():
    if request.method == 'OPTIONS':
        # Handle preflight request
        response = jsonify({'message': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response
    if request.method == 'GET':
        return jsonify({
            'status': 'Backend is running', 
            'message': 'Send POST requests to /send-pdf-email endpoint',
            'timestamp': datetime.now().isoformat()
    })
    
    # Redirect POST requests to the actual endpoint
    return send_pdf_email()

@app.route('/send-pdf-email', methods=['GET', 'POST', 'OPTIONS'])

def send_pdf_email():

    if request.method == 'OPTIONS':
        # Handle preflight request
        response = jsonify({'message': 'OK'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response

    if request.method == 'GET':
        return jsonify({
            'status': 'Email endpoint is running', 
            'message': 'Send POST requests with email data to this endpoint'
        })

    data = request.get_json()
    recipient_email = data.get('recipient_email')
    pdf_base64 = data.get('pdf_base64')
    report_details = data.get('report_details', {})

    # Basic validation for essential data
    if not recipient_email or not pdf_base64:
        return jsonify({'error': 'Missing recipient email or PDF data.'}), 400

    if not all([MAILCHIMP_API_KEY, MAILCHIMP_SERVER_PREFIX, MAILCHIMP_AUDIENCE_ID, EMAIL_HOST, EMAIL_PORT, EMAIL_USERNAME, EMAIL_PASSWORD, COMPANY_BCC_EMAIL]):
        return jsonify({'error': 'Server configuration is incomplete. Please check environment variables.'}), 500

    try:
        # 1. Subscribe to Mailchimp (Optional: You can remove this block if Mailchimp integration isn't needed)
        try:
            mailchimp.lists.add_list_member(MAILCHIMP_AUDIENCE_ID, {
                "email_address": recipient_email,
                "status": "subscribed", # or "pending" for double opt-in
                "merge_fields": {
                    "FNAME": "Customer", # You could add input for this on frontend
                    "LNAME": "HCO Calc"
                }
            })
            print(f"Subscribed {recipient_email} to Mailchimp.")
        except MailchimpClient.ApiError as e:
            # Handle specific Mailchimp API errors (e.g., member exists)
            print(f"Mailchimp API error for {recipient_email}: {e.text}")
            # You might want to log this but still proceed with email if it's just a "member exists" error
            if "Member Exists" not in e.text: # Or check e.status for specific HTTP codes
                return jsonify({'error': f"Mailchimp subscription failed: {e.text}"}), 500
        except Exception as e:
            print(f"Generic Mailchimp error for {recipient_email}: {e}")
            return jsonify({'error': f"Mailchimp subscription failed: {str(e)}"}), 500


        # 2. Prepare and Send Email
        msg = MIMEMultipart()
        msg['From'] = EMAIL_USERNAME
        msg['To'] = recipient_email
        msg['Subject'] = f"Dam Buster HCO Calculator Report - {report_details.get('sumpLabel', 'Untitled Sump')}"
        msg['Bcc'] = COMPANY_BCC_EMAIL

        # Email body (can be HTML for better formatting)
        body = f"""
        Dear Customer,

        Please find attached your Dam Buster HCO Calculator report for:
        Job Number: {report_details.get('jobNumber', 'N/A')}
        Project Name: {report_details.get('projectName', 'N/A')}
        Sump Label: {report_details.get('sumpLabel', 'N/A')}

        --- Calculation Summary ---
        Total Design Flow Rate: {report_details.get('totalFlowRate', 'N/A')}
        Sump Depth: {report_details.get('sumpDepth', 'N/A')}
        Recommended HCO Size: {report_details.get('hcoSize', 'N/A')}

        Best regards,
        The Dam Buster Team
        """
        msg.attach(MIMEText(body, 'plain')) # or 'html'

        # Attach PDF
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(base64.b64decode(pdf_base64))
        encoders.encode_base64(part)
        
        # Create a safe filename for the PDF attachment
        safe_job_number = report_details.get('jobNumber', 'NoJob').replace(' ', '_').replace('/', '-')
        safe_sump_label = report_details.get('sumpLabel', 'Report').replace(' ', '_').replace('/', '-')
        current_date_filename = datetime.now().strftime('%Y%m%d') # YYYYMMDD
        
        filename = f"HCO_Report_{safe_job_number}_{safe_sump_label}_{current_date_filename}.pdf"
        part.add_header('Content-Disposition', f"attachment; filename=\"{filename}\"")
        msg.attach(part)

        # Connect to SMTP server and send
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls() # Use TLS for encryption
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            # sendmail takes from_addr, to_addrs (list of recipients), msg_string
            # It's crucial to pass all recipients (To and Bcc) in a list to sendmail
            all_recipients = [recipient_email, COMPANY_BCC_EMAIL]
            server.sendmail(EMAIL_USERNAME, all_recipients, msg.as_string())

        return jsonify({'message': 'PDF report sent successfully!'}), 200

    except Exception as e:
        print(f"Error sending email: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
