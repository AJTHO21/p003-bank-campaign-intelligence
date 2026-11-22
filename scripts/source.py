from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/uci-222"
URL = "https://archive.ics.uci.edu/static/public/222/bank%2Bmarketing.zip"
ARCHIVE = "bank-marketing.zip"
INNER = "bank-additional.zip"
CSV = "bank-additional-full.csv"
README = "bank-additional-names.txt"
MANIFEST = "manifest.json"
ROWS = 41188


def digest(path):
    return sha256(path.read_bytes()).hexdigest()
