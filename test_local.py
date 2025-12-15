import inference
import os

# Ensure test image exists
if not os.path.exists("test_images/zidane.jpg"):
    print("Error: test_images/zidane.jpg not found")
    exit(1)

with open("test_images/zidane.jpg", "rb") as f:
    img_bytes = f.read()

print("Running inference...")
# This will trigger model download on first run
detections, annotated_bytes = inference.run_inference(img_bytes)

print(f"Detections found: {len(detections)}")
for d in detections:
    print(f" - {d['label']} ({d['confidence']:.2f})")

output_path = "test_images/zidane_annotated.jpg"
with open(output_path, "wb") as f:
    f.write(annotated_bytes)
print(f"Saved annotated image to {output_path}")
