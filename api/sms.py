import requests
from django.conf import settings

def format_phone(phone):
    if phone.startswith("07"):
        return "+254" + phone[1:]
    return phone

def send_sms(phone, message):
    url = "https://api.africastalking.com/version1/messaging"

    headers = {
        "apiKey": settings.AT_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }

    data = {
        "username": settings.AT_USERNAME,
        "to": format_phone(phone),
        "message": message
    }

    response = requests.post(url, headers=headers, data=data)

    print(response.text)  # debug
    return response.json()