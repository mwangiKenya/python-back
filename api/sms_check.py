import requests

url = "https://api.africastalking.com/version1/user"

headers = {
    "apiKey": "PASTE_YOUR_KEY_HERE",
    "Accept": "application/json"
}

params = {
    "username": "sandbox"
}

response = requests.get(url, headers=headers, params=params)

print("STATUS:", response.status_code)
print("RESPONSE:", response.text)