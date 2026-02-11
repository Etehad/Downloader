from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import mimetypes

app = Flask(__name__)

def get_file_size(url):
    """دریافت حجم فایل از هدر بدون دانلود کامل"""
    try:
        response = requests.head(url, timeout=10, allow_redirects=True)
        size = response.headers.get('content-length')
        if size:
            size_mb = int(size) / (1024 * 1024)
            return f"{size_mb:.2f} MB"
        return "نامشخص"
    except:
        return "نامشخص"

def get_media_type(url):
    """تشخیص نوع فایل"""
    ext = url.split('.')[-1].split('?')[0].lower()
    
    video_exts = ['mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'm4v']
    audio_exts = ['mp3', 'wav', 'ogg', 'aac', 'm4a', 'flac', 'wma']
    image_exts = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp', 'ico']
    
    if ext in video_exts:
        return 'video'
    elif ext in audio_exts:
        return 'audio'
    elif ext in image_exts:
        return 'image'
    else:
        return 'unknown'

def extract_media(url):
    """استخراج تمام فایل‌های مدیا از صفحه"""
    try:
        # دریافت محتوای صفحه
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        base_url = url
        
        media_files = []
        
        # استخراج ویدیوها
        for video in soup.find_all('video'):
            # از تگ source
            for source in video.find_all('source'):
                src = source.get('src')
                if src:
                    full_url = urljoin(base_url, src)
                    media_files.append({
                        'url': full_url,
                        'type': 'video',
                        'size': get_file_size(full_url)
                    })
            
            # از خود تگ video
            src = video.get('src')
            if src:
                full_url = urljoin(base_url, src)
                media_files.append({
                    'url': full_url,
                    'type': 'video',
                    'size': get_file_size(full_url)
                })
        
        # استخراج آهنگ‌ها
        for audio in soup.find_all('audio'):
            # از تگ source
            for source in audio.find_all('source'):
                src = source.get('src')
                if src:
                    full_url = urljoin(base_url, src)
                    media_files.append({
                        'url': full_url,
                        'type': 'audio',
                        'size': get_file_size(full_url)
                    })
            
            # از خود تگ audio
            src = audio.get('src')
            if src:
                full_url = urljoin(base_url, src)
                media_files.append({
                    'url': full_url,
                    'type': 'audio',
                    'size': get_file_size(full_url)
                })
        
        # استخراج تصاویر
        for img in soup.find_all('img'):
            src = img.get('src')
            if src:
                full_url = urljoin(base_url, src)
                # فیلتر کردن تصاویر خیلی کوچک (احتمالا آیکون)
                media_files.append({
                    'url': full_url,
                    'type': 'image',
                    'size': get_file_size(full_url)
                })
        
        # جستجو در تگ‌های a برای فایل‌های مدیا
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            full_url = urljoin(base_url, href)
            media_type = get_media_type(full_url)
            
            if media_type in ['video', 'audio', 'image']:
                media_files.append({
                    'url': full_url,
                    'type': media_type,
                    'size': get_file_size(full_url)
                })
        
        # حذف تکراری‌ها
        unique_files = []
        seen_urls = set()
        for file in media_files:
            if file['url'] not in seen_urls:
                seen_urls.add(file['url'])
                unique_files.append(file)
        
        return unique_files
        
    except requests.exceptions.RequestException as e:
        raise Exception(f"خطا در دریافت صفحه: {str(e)}")
    except Exception as e:
        raise Exception(f"خطا در پردازش: {str(e)}")

@app.route('/', methods=['GET'])
def extract_media_api():
    """API endpoint برای استخراج فایل‌های مدیا"""
    
    # دریافت URL از پارامتر
    target_url = request.args.get('url')
    
    if not target_url:
        return jsonify({
            'success': False,
            'error': 'پارامتر url الزامی است',
            'usage': 'https://your-app.render.com?url=https://example.com'
        }), 400
    
    # بررسی اعتبار URL
    try:
        result = urlparse(target_url)
        if not all([result.scheme, result.netloc]):
            raise ValueError
    except:
        return jsonify({
            'success': False,
            'error': 'URL نامعتبر است'
        }), 400
    
    try:
        # استخراج فایل‌ها
        media_files = extract_media(target_url)
        
        # دسته‌بندی بر اساس نوع
        categorized = {
            'videos': [f for f in media_files if f['type'] == 'video'],
            'audios': [f for f in media_files if f['type'] == 'audio'],
            'images': [f for f in media_files if f['type'] == 'image']
        }
        
        return jsonify({
            'success': True,
            'url': target_url,
            'total_files': len(media_files),
            'media': categorized,
            'all_files': media_files
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
