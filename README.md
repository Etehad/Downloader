# Media Extractor API

API استخراج ویدیو، تصویر و فایل صوتی از صفحات وب

## استفاده

GET /
?url=https://example.com/page

## خروجی

- url: لینک دانلود
- type: video | audio | image
- size_mb: حجم فایل (MB)

## مثال

https://your-app.onrender.com?url=https://www.w3schools.com/html/html5_video.asp
