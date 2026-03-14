import requests
from django.conf import settings

def send_sms(phone_number, message):
    url = "https://api.africastalking.com/version1/messaging"

    headers = {
        "apiKey": settings.AT_API_KEY.strip(),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }

    data = {
        "username": settings.AT_USERNAME.strip(),  # must be "sandbox"
        "to": phone_number,
        "message": message
    }

    response = requests.post(url, headers=headers, data=data)

    print("STATUS:", response.status_code)
    print("RAW RESPONSE:", response.text)

    try:
        return response.json()
    except:
        return {"error": response.text}