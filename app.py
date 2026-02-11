from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import os
import re

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.google.com/"
}

# فرمت‌های ویدیویی
VIDEO_EXTENSIONS = (
    'mp4', 'mkv', 'webm', 'avi', 'mov', 'flv', 
    'wmv', 'mpg', 'mpeg', 'm4v', '3gp', 'ts', 
    'm3u8', 'mpd'  # streaming formats
)

def is_video_url(url):
    url_lower = url.lower().split('?')[0].split('#')[0]
    return any(url_lower.endswith(f'.{ext}') for ext in VIDEO_EXTENSIONS)

def detect_video_type(url):
    """تشخیص نوع ویدیو"""
    url_lower = url.lower()
    
    if '.m3u8' in url_lower:
        return 'hls_stream'
    elif '.mpd' in url_lower:
        return 'dash_stream'
    elif any(ext in url_lower for ext in ['.mp4', '.webm', '.mkv', '.avi']):
        return 'direct_download'
    else:
        return 'unknown'

def get_file_info(url, video_type):
    try:
        response = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=10)
        
        size_bytes = response.headers.get('Content-Length')
        size_mb = round(int(size_bytes) / (1024 * 1024), 2) if size_bytes else None
        
        content_type = response.headers.get('Content-Type', '').split(';')[0]
        
        quality = extract_quality(url)
        
        # برای HLS/DASH، اطلاعات بیشتر
        if video_type in ['hls_stream', 'dash_stream']:
            return {
                'size_mb': 'streaming',
                'content_type': content_type,
                'quality': quality,
                'downloadable': False,
                'note': 'نیاز به دانلود با ffmpeg/yt-dlp'
            }
        
        return {
            'size_mb': size_mb,
            'content_type': content_type,
            'quality': quality,
            'downloadable': True,
            'note': 'قابل دانلود مستقیم'
        }
    except:
        return {
            'size_mb': None,
            'content_type': 'unknown',
            'quality': extract_quality(url),
            'downloadable': 'unknown',
            'note': 'نیاز به بررسی دستی'
        }

def extract_quality(url):
    quality_patterns = [
        r'(\d{3,4})p',
        r'(\d{3,4})x(\d{3,4})',
    ]
    
    for pattern in quality_patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(0)
    
    return 'unknown'

def extract_from_network_requests(page_url, html_content):
    """استخراج URLهای ویدیو از درخواست‌های شبکه در JavaScript"""
    video_urls = []
    
    # پیدا کردن همه URLهای احتمالی در JavaScript
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
    
    # 1. تگ‌های video و source
    for video_tag in soup.find_all(['video', 'source']):
        src = video_tag.get('src')
        if src:
            full_url = urljoin(page_url, src)
            if full_url not in seen_urls and is_video_url(full_url):
                seen_urls.add(full_url)
                video_type = detect_video_type(full_url)
                videos.append({
                    'url': full_url,
                    'source': 'html_tag',
                    'type': video_type,
                    **get_file_info(full_url, video_type)
                })
    
    # 2. لینک‌های a
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if is_video_url(href):
            full_url = urljoin(page_url, href)
            if full_url not in seen_urls:
                seen_urls.add(full_url)
                video_type = detect_video_type(full_url)
                videos.append({
                    'url': full_url,
                    'source': 'anchor_tag',
                    'type': video_type,
                    **get_file_info(full_url, video_type)
                })
    
    # 3. data attributes
    for elem in soup.find_all(attrs=re.compile(r'data-(video|src|url)')):
        for attr, value in elem.attrs.items():
            if 'video' in attr.lower() or 'src' in attr.lower():
                if is_video_url(str(value)):
                    full_url = urljoin(page_url, value)
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        video_type = detect_video_type(full_url)
                        videos.append({
                            'url': full_url,
                            'source': f'data_attribute_{attr}',
                            'type': video_type,
                            **get_file_info(full_url, video_type)
                        })
    
    # 4. استخراج از JavaScript
    js_urls = extract_from_network_requests(page_url, html_content)
    for url in js_urls:
        full_url = urljoin(page_url, url)
        if full_url not in seen_urls and is_video_url(full_url):
            seen_urls.add(full_url)
            video_type = detect_video_type(full_url)
            videos.append({
                'url': full_url,
                'source': 'javascript',
                'type': video_type,
                **get_file_info(full_url, video_type)
            })
    
    return videos

@app.route("/", methods=["GET"])
def extract_videos():
    target_url = request.args.get("url")
    
    if not target_url:
        return jsonify({
            "success": False,
            "error": "پارامتر url الزامی است",
            "usage": "/?url=https://example.com/video-page"
        }), 400
    
    parsed = urlparse(target_url)
    if not parsed.scheme or not parsed.netloc:
        return jsonify({
            "success": False,
            "error": "فرمت URL نامعتبر است"
        }), 400
    
    try:
        response = requests.get(target_url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        
        videos = extract_videos_from_html(target_url, response.text)
        
        # دسته‌بندی بر اساس نوع
        direct_videos = [v for v in videos if v.get('downloadable') == True]
        stream_videos = [v for v in videos if v.get('type') in ['hls_stream', 'dash_stream']]
        unknown_videos = [v for v in videos if v.get('downloadable') == 'unknown']
        
        return jsonify({
            "success": True,
            "target_url": target_url,
            "total_videos": len(videos),
            "summary": {
                "direct_download": len(direct_videos),
                "streaming": len(stream_videos),
                "unknown": len(unknown_videos)
            },
            "videos": {
                "direct_download": direct_videos,
                "streaming": stream_videos,
                "unknown": unknown_videos
            },
            "download_guide": {
                "direct": "استفاده از wget یا curl",
                "streaming": "استفاده از yt-dlp یا ffmpeg",
                "command_example": "yt-dlp 'URL' یا ffmpeg -i 'URL' output.mp4"
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/download-guide")
def download_guide():
    return jsonify({
        "guide": {
            "direct_download": {
                "description": "فایل‌های .mp4, .webm, .mkv",
                "method": "دانلود مستقیم با مرورگر یا wget",
                "example": "wget 'https://example.com/video.mp4'"
            },
            "hls_stream": {
                "description": "فایل‌های .m3u8",
                "method": "استفاده از ffmpeg یا yt-dlp",
                "example": "ffmpeg -i 'URL.m3u8' -c copy output.mp4"
            },
            "dash_stream": {
                "description": "فایل‌های .mpd",
                "method": "استفاده از yt-dlp",
                "example": "yt-dlp 'URL.mpd'"
            },
            "drm_protected": {
                "description": "ویدیوهای رمزگذاری شده",
                "method": "غیرممکن بدون کلید رمزگشایی",
                "note": "قانونی نیست"
            }
        }
    }), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
