from flask import Flask
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
import re
import subprocess
import tempfile
import logging
from threading import Thread

app = Flask(__name__)

# تنظیمات لاگ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# توکن ربات تلگرام
TELEGRAM_TOKEN = "8288294909:AAGOU8C69S1v_RRxy6QX4dVbxVrVWQOgdME"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.google.com/"
}

VIDEO_EXTENSIONS = (
    'mp4', 'mkv', 'webm', 'avi', 'mov', 'flv', 
    'wmv', 'mpg', 'mpeg', 'm4v', '3gp', 'ts', 
    'm3u8', 'mpd'
)

def send_telegram_message(chat_id, text, reply_to_message_id=None):
    """ارسال پیام به تلگرام"""
    url = f"{TELEGRAM_API}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "reply_to_message_id": reply_to_message_id
    }
    response = requests.post(url, json=data)
    return response.json()

def delete_telegram_message(chat_id, message_id):
    """حذف پیام در تلگرام"""
    url = f"{TELEGRAM_API}/deleteMessage"
    data = {
        "chat_id": chat_id,
        "message_id": message_id
    }
    requests.post(url, json=data)

def send_telegram_video(chat_id, video_path, caption="", reply_to_message_id=None):
    """ارسال ویدیو به تلگرام با استفاده از premium method (بدون محدودیت 50MB)"""
    url = f"{TELEGRAM_API}/sendDocument"
    
    with open(video_path, 'rb') as video_file:
        files = {'document': video_file}
        data = {
            'chat_id': chat_id,
            'caption': caption,
            'reply_to_message_id': reply_to_message_id
        }
        response = requests.post(url, files=files, data=data)
    
    return response.json()

def is_video_url(url):
    url_lower = url.lower().split('?')[0].split('#')[0]
    return any(url_lower.endswith(f'.{ext}') for ext in VIDEO_EXTENSIONS)

def detect_video_type(url):
    url_lower = url.lower()
    
    if '.m3u8' in url_lower:
        return 'hls_stream'
    elif '.mpd' in url_lower:
        return 'dash_stream'
    elif any(ext in url_lower for ext in ['.mp4', '.webm', '.mkv', '.avi']):
        return 'direct_download'
    else:
        return 'unknown'

def extract_quality(url):
    quality_patterns = [
        r'(\d{3,4})p',
        r'(\d{3,4})x(\d{3,4})',
    ]
    
    for pattern in quality_patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            number = match.group(1)
            if number.isdigit():
                return f"{number}p"
    
    return 'unknown'

def extract_from_network_requests(page_url, html_content):
    video_urls = []
    
    js_patterns = [
        r'["\']([^"\']*\.m3u8[^"\']*)["\']',
        r'["\']([^"\']*\.mpd[^"\']*)["\']',
        r'["\']([^"\']*\.mp4[^"\']*)["\']',
        r'["\']([^"\']*\.webm[^"\']*)["\']',
        r'src:\s*["\']([^"\']+)["\']',
        r'file:\s*["\']([^"\']+)["\']',
        r'video:\s*["\']([^"\']+)["\']',
    ]
    
    for pattern in js_patterns:
        matches = re.findall(pattern, html_content, re.IGNORECASE)
        video_urls.extend(matches)
    
    return video_urls

def extract_videos_from_html(page_url, html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    videos = []
    seen_urls = set()
    
    # تگ‌های video و source
    for video_tag in soup.find_all(['video', 'source']):
        src = video_tag.get('src')
        if src:
            full_url = urljoin(page_url, src)
            if full_url not in seen_urls and is_video_url(full_url):
                seen_urls.add(full_url)
                video_type = detect_video_type(full_url)
                if video_type in ['hls_stream', 'dash_stream']:
                    videos.append({
                        'url': full_url,
                        'type': video_type,
                        'quality': extract_quality(full_url)
                    })
    
    # لینک‌های a
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if is_video_url(href):
            full_url = urljoin(page_url, href)
            if full_url not in seen_urls:
                seen_urls.add(full_url)
                video_type = detect_video_type(full_url)
                if video_type in ['hls_stream', 'dash_stream']:
                    videos.append({
                        'url': full_url,
                        'type': video_type,
                        'quality': extract_quality(full_url)
                    })
    
    # data attributes
    for elem in soup.find_all(attrs=re.compile(r'data-(video|src|url)')):
        for attr, value in elem.attrs.items():
            if 'video' in attr.lower() or 'src' in attr.lower():
                if is_video_url(str(value)):
                    full_url = urljoin(page_url, value)
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        video_type = detect_video_type(full_url)
                        if video_type in ['hls_stream', 'dash_stream']:
                            videos.append({
                                'url': full_url,
                                'type': video_type,
                                'quality': extract_quality(full_url)
                            })
    
    # استخراج از JavaScript
    js_urls = extract_from_network_requests(page_url, html_content)
    for url in js_urls:
        full_url = urljoin(page_url, url)
        if full_url not in seen_urls and is_video_url(full_url):
            seen_urls.add(full_url)
            video_type = detect_video_type(full_url)
            if video_type in ['hls_stream', 'dash_stream']:
                videos.append({
                    'url': full_url,
                    'type': video_type,
                    'quality': extract_quality(full_url)
                })
    
    return videos

def download_video_with_ffmpeg(stream_url, output_path):
    """دانلود ویدیو با ffmpeg"""
    try:
        cmd = [
            'ffmpeg',
            '-i', stream_url,
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            '-y',
            output_path
        ]
        
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        return True
    except Exception as e:
        logger.error(f"خطا در دانلود با ffmpeg: {e}")
        return False

def process_video_request(chat_id, message_id, target_url):
    """پردازش درخواست ویدیو"""
    # ارسال پیام در حال پردازش
    processing_msg = send_telegram_message(chat_id, "🔄 در حال پردازش...", message_id)
    processing_msg_id = processing_msg.get('result', {}).get('message_id')
    
    try:
        # دریافت صفحه
        response = requests.get(target_url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        
        # استخراج ویدیوها
        videos = extract_videos_from_html(target_url, response.text)
        
        # فیلتر کردن ویدیوهای 720p
        video_720p = None
        for video in videos:
            quality = video.get('quality', '').lower()
            if '720' in quality or quality == '720p':
                video_720p = video
                break
        
        if not video_720p:
            delete_telegram_message(chat_id, processing_msg_id)
            send_telegram_message(chat_id, "❌ ویدیوی 720p پیدا نشد!", message_id)
            return
        
        # دانلود ویدیو
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_path = temp_file.name
        
        success = download_video_with_ffmpeg(video_720p['url'], temp_path)
        
        if success and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            # ارسال ویدیو
            send_telegram_video(
                chat_id, 
                temp_path, 
                caption=f"✅ ویدیو 720p\n🔗 منبع: {target_url[:50]}...",
                reply_to_message_id=message_id
            )
            
            # حذف فایل موقت
            os.unlink(temp_path)
        else:
            send_telegram_message(chat_id, "❌ خطا در دانلود ویدیو!", message_id)
        
        # حذف پیام پردازش
        delete_telegram_message(chat_id, processing_msg_id)
        
    except Exception as e:
        logger.error(f"خطا در پردازش: {e}")
        delete_telegram_message(chat_id, processing_msg_id)
        send_telegram_message(chat_id, f"❌ خطا: {str(e)}", message_id)

@app.route(f"/{TELEGRAM_TOKEN}", methods=['POST'])
def telegram_webhook():
    """وب‌هوک تلگرام"""
    try:
        update = requests.get_json()
        
        if 'message' not in update:
            return 'ok'
        
        message = update['message']
        chat_id = message['chat']['id']
        message_id = message['message_id']
        text = message.get('text', '')
        
        # بررسی لینک
        url_match = None
        
        # بررسی پیام‌های شروع با https
        if text.startswith('http'):
            url_match = text.strip()
        
        # بررسی پیام‌های "دانلود ..."
        download_pattern = r'دانلود\s+(https?://[^\s]+)'
        match = re.search(download_pattern, text)
        if match:
            url_match = match.group(1)
        
        if url_match:
            # پردازش در thread جداگانه
            thread = Thread(target=process_video_request, args=(chat_id, message_id, url_match))
            thread.start()
        
        return 'ok'
    
    except Exception as e:
        logger.error(f"خطا در webhook: {e}")
        return 'error', 500

@app.route("/health")
def health():
    return {"status": "ok"}, 200

@app.route("/set-webhook")
def set_webhook():
    """تنظیم وب‌هوک"""
    webhook_url = request.args.get('url')
    if not webhook_url:
        return {"error": "url parameter required"}, 400
    
    full_webhook_url = f"{webhook_url}/{TELEGRAM_TOKEN}"
    response = requests.post(f"{TELEGRAM_API}/setWebhook", json={"url": full_webhook_url})
    
    return response.json()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
