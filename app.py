from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

VIDEO_EXT = ("mp4", "mkv", "webm", "avi", "mov")
AUDIO_EXT = ("mp3", "wav", "ogg", "aac", "m4a")
IMAGE_EXT = ("jpg", "jpeg", "png", "gif", "webp", "svg")

def file_type(url):
    ext = url.split("?")[0].split(".")[-1].lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in IMAGE_EXT:
        return "image"
    return None

def file_size(url):
    try:
        r = requests.head(url, allow_redirects=True, timeout=10)
        size = r.headers.get("Content-Length")
        if size:
            return round(int(size) / (1024 * 1024), 2)
    except:
        pass
    return None

def extract_media(page_url):
    r = requests.get(page_url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")  # ← تغییر از lxml به html.parser

    results = []
    seen = set()

    tags = []

    tags += [img.get("src") for img in soup.find_all("img")]
    tags += [v.get("src") for v in soup.find_all("video")]
    tags += [a.get("src") for a in soup.find_all("audio")]
    tags += [s.get("src") for s in soup.find_all("source")]
    tags += [a.get("href") for a in soup.find_all("a")]

    for src in tags:
        if not src:
            continue

        full_url = urljoin(page_url, src)
        if full_url in seen:
            continue

        ftype = file_type(full_url)
        if not ftype:
            continue

        seen.add(full_url)

        results.append({
            "url": full_url,
            "type": ftype,
            "size_mb": file_size(full_url)
        })

    return results

@app.route("/", methods=["GET"])
def api():
    target_url = request.args.get("url")

    if not target_url:
        return jsonify({
            "success": False,
            "error": "پارامتر url الزامی است"
        }), 400

    parsed = urlparse(target_url)
    if not parsed.scheme or not parsed.netloc:
        return jsonify({
            "success": False,
            "error": "URL نامعتبر است"
        }), 400

    try:
        media = extract_media(target_url)
        return jsonify({
            "success": True,
            "count": len(media),
            "media": media
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
