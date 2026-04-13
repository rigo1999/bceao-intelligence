import requests
import time

def test_api():
    print("Testing API /chat endpoint...")
    url = "http://localhost:8000/chat"
    payload = {"question": "C'est quoi la BCEAO ?"}
    
    start = time.time()
    try:
        # Use stream=True because it's a streaming response
        with requests.post(url, json=payload, stream=True, timeout=30) as r:
            print(f"Status Code: {r.status_code}")
            for line in r.iter_lines():
                if line:
                    print(f"Received: {line.decode('utf-8')}")
                    # Stop after first few tokens to save time
                    if "data: " in line.decode('utf-8'):
                        break
        print(f"Total time for first token: {time.time() - start:.4f}s")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_api()
