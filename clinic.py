from flask import Flask, request, jsonify

app = Flask(__name__)

# --- 1. Safaricom Daraja STK Push Callback ---
@app.route('/api/mpesa/callback', methods=['POST'])
def mpesa_callback():
    data = request.get_json()
    
    # Extract STK push payload details
    stk_callback = data.get('Body', {}).get('stkCallback', {})
    result_code = stk_callback.get('ResultCode')
    checkout_request_id = stk_callback.get('CheckoutRequestID')
    
    if result_code == 0:
        # Payment was successful! Update patient payment status in SQLite database here
        items = stk_callback.get('CallbackMetadata', {}).get('Item', [])
        # Extract metadata (amount, receipt number, phone number)
        print(f"Payment Successful for CheckoutID: {checkout_request_id}")
    else:
        # Payment failed or was canceled by user
        print(f"Payment failed with code {result_code}: {stk_callback.get('ResultDesc')}")
        
    # Always respond with 200 OK JSON to confirm receipt to Safaricom
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200


# --- 2. Africa's Talking SMS Delivery / Incoming Callback ---
@app.route('/api/at/sms/callback', methods=['POST'])
def africastalking_sms_callback():
    # Africa's Talking sends notifications as application/x-www-form-urlencoded
    status = request.form.get('status')
    message_id = request.form.get('id')
    phone_number = request.form.get('phoneNumber')
    
    print(f"SMS Status to {phone_number}: {status} (ID: {message_id})")
    
    # Acknowledge receipt
    return jsonify({"status": "success"}), 200
