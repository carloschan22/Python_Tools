import time

# Use a pipeline as a high-level helper
from transformers import pipeline

pipe = pipeline("image-text-to-text", model="Qwen/Qwen3-VL-2B-Instruct")

messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "image",
                "url": "C:/Users/carlo/Downloads/ScreenShot_2026-01-19_104301_237.jpg",
            },
            {
                "type": "text",
                "text": "In the picture, there are 24 material acupuncture points on the tray, and each material has a green feature. Please count the total quantity of all materials with green characteristics on the pallet. Just answer with a number.",
            },
        ],
    },
]

start_time = time.time()
result = pipe(text=messages)
end_time = time.time()
time_taken = round(end_time - start_time, 2)
answer = result[0]["generated_text"][1]["content"]

print(f"Answer: {answer}, Takes: {time_taken}s")
