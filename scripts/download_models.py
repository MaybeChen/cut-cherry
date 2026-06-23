from pathlib import Path
print("Model downloads are explicit. Configure URLs/paths, then place weights under ./models (not at import time).")
Path("models").mkdir(exist_ok=True)
