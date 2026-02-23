import requests

url = "http://localhost:8000/generate"
payload = {"prompt": "America's Financial Crisis: What You Need to Know Now"}

response = requests.post(url, params=payload)

print("Status Code:", response.status_code)
print("Response:")
print(response.text)
