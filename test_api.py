import requests
import base64
import os

url = "http://localhost:8000/predict"
image_path = "test_images/zidane.jpg"

if not os.path.exists(image_path):
    print(f"Error: {image_path} not found")
    exit(1)

print(f"Sending {image_path} to {url}...")
try:
    with open(image_path, "rb") as f:
        files = {"file": f}
        response = requests.post(url, files=files)

    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Detections: {len(data['detections'])}")
        for d in data['detections']:
            print(f" - {d['label']} ({d['confidence']:.2f})")
        
        # Check if image is valid base64
        img_bytes = base64.b64decode(data["image"])
        print(f"Received annotated image: {len(img_bytes)} bytes")
        
        output_path = "test_images/api_result.jpg"
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        print(f"Saved API result to {output_path}")
    else:
        print("Error Response:", response.text)
except Exception as e:
    print(f"Request failed: {e}")
