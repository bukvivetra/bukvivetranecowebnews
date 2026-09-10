import os
import re
import json
import hashlib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# === НАСТРОЙКИ ===
RSS_URL = "https://lenta.ru/rss/news"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
OUTPUT_FILE = "index.html"
NEWS_JSON = "news.json"
NEWS_DIR = "news"
SITEMAP_FILE = "sitemap.xml"
BASE_URL = "https://bukvivetra.github.io/bukvivetranecowebnews/"
MAX_NEWS_PER_RUN = 3
INDEX_SHOW_LIMIT = 50
MODEL_NAME = "openai/gpt-oss-120b"
MIN_TEXT_LENGTH = 120
MAX_TITLE_OVERLAP = 0.7

BAD_PATTERNS = [
    "пришлите", "предоставьте", "предоставлен", "укажите текст",
    "не могу переписать", "переписать её невозможно", "переписать невозможно",
    "нужен текст", "я не могу", "извините", "прошу прощения",
    "не имею доступа", "текст не предоставлен", "текст новости не",
    "невозможно", "не предоставлен"
]

CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f0f2f5; color: #333; }
header { background: #1a1a2e; color: white; padding: 20px; border-radius: 12px; margin-bottom: 24px; text-align: center; }
header h1 { margin: 0; font-size: 28px; }
header a.back { color: #fff; text-decoration: none; font-size: 16px; }
.news-list { list-style: none; padding: 0; margin: 0; }
.news-list li { background: white; margin-bottom: 16px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); transition: box-shadow 0.2s; }
.news-list li:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.12); }
.news-list li a { display: block; padding: 20px 24px; text-decoration: none; color: inherit; }
.news-list li h2 { margin: 0 0 8px; color: #1a1a2e; font-size: 18px; line-height: 1.4; }
.article { background: white; padding: 24px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.article h1 { color: #1a1a2e; margin-top: 0; font-size: 24px; line-height: 1.4; }
.article p { line-height: 1.7; color: #444; }
.source { font-size: 13px; color: #888; margin-top: 12px; padding-top: 12px; border-top: 1px solid #eee; }
.source a { color: #0066cc; text-decoration: none; }
.date { font-size: 12px; color: #aaa; margin-top: 4px; }
"""

def make_slug(title):
    h = hashlib.md5(title.encode("utf-8")).hexdigest()[:10]
    return f"n-{h}"

def escape_html(text):
    if text is None:
        return ""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

def escape_xml(text):
    if text is None:
        return ""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))

def load_existing_news():
    if os.path.exists(NEWS_JSON):
        with open(NEWS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_news(news_list):
    with open(NEWS_JSON, "w", encoding="utf-8") as f:
        json.dump(news_list, f, ensure_ascii=False, indent=2)

def get_rss_news():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    response = requests.get(RSS_URL, headers=headers, timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    news = []
    for item in root.findall(".//item"):
        news.append({
            "title": item.find("title").text,
            "description": item.find("description").text,
            "link": item.find("link").text,
            "pub_date": item.find("pubDate").text if item.find("pubDate") is not None else ""
        })
    return news

def clean_text(text):
    text = re.sub(r"\*\*Заголовок:\*\*\s*", "", text)
    text = re.sub(r"\*\*Текст:\*\*\s*", "", text)
    text = re.sub(r"\*\*", "", text)
    return text.strip()

def title_overlap(title, text):
    def normalize(s):
        return re.findall(r"[а-яёa-z0-9]+", s.lower())
    title_words = set(normalize(title))
    text_words = set(normalize(text))
    if not title_words:
        return 0
    return len(title_words & text_words) / len(title_words)

def is_bad_response(text, title):
    if not text or len(text) < MIN_TEXT_LENGTH:
        return True
    if any(p in text.lower() for p in BAD_PATTERNS):
        return True
    if title_overlap(title, text) > MAX_TITLE_OVERLAP:
        return True
    return False

def rewrite_with_ai(title, description):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "Ты — опытный редактор новостного издания. Ты переписываешь новости своими словами на русском языке: сохраняешь все ключевые факты, но меняешь структуру предложений и лексику. Пиши развёрнуто, 3-5 предложений. Отвечай ТОЛЬКО готовым текстом новости — без приветствий, пояснений, вопросов, без пометок 'Заголовок:' и 'Текст:', без markdown."},
            {"role": "user", "content": f"Перепиши эту новость:\n\nЗаголовок: {title}\n\nТекст: {description}"}
        ],
        "temperature": 0.7
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        if response.status_code == 200:
            text = clean_text(response.json()['choices'][0]['message']['content'].strip())
            if is_bad_response(text, title):
                print("  → ИИ вернул некачественный текст, пропускаем")
                return None
            return text
        print(f"  → Ошибка ИИ: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        print(f"  → Ошибка при запросе к ИИ: {e}")
        return None

def render_article_page(n):
    title = escape_html(n['title'])
    body = escape_html(n['rewritten'])
    link = escape_html(n['link'])
    date = escape_html(n.get('date', ''))
    desc = escape_html(n['rewritten'][:160])
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="{desc}">
<title>{title} — Новости дня</title>
<style>{CSS}</style>
</head>
<body>
<header><a href="../" class="back">← Все новости</a></header>
<article class="article">
<h1>{title}</h1>
<div class="date">{date}</div>
<p>{body}</p>
<div class="source">Источник: <a href="{link}" target="_blank" rel="noopener nofollow">Lenta.ru</a></div>
</article>
</body>
</html>"""

def render_index(news_list):
    items = ""
    for n in news_list[:INDEX_SHOW_LIMIT]:
        slug = n.get('slug') or make_slug(n['title'])
        items += f"""
    <li><a href="news/{slug}.html">
        <h2>{escape_html(n['title'])}</h2>
        <div class="date">{escape_html(n.get('date',''))}</div>
    </a></li>"""
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="Актуальные новости России и мира. Автоматическое обновление каждый час.">
<title>Новости дня</title>
<style>{CSS}</style>
</head>
<body>
<header><h1>Новости дня</h1></header>
<ul class="news-list">{items}
</ul>
</body>
</html>"""

def render_sitemap(news_list):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
             f'  <url><loc>{BASE_URL}</loc><lastmod>{today}</lastmod>'
             f'<changefreq>hourly</changefreq><priority>1.0</priority></url>']
    for n in news_list:
        slug = n.get('slug') or make_slug(n['title'])
        iso = (n.get('date','') or today).split(' ')[0]
        url = f"{BASE_URL}news/{slug}.html"
        parts.append(f'  <url><loc>{escape_xml(url)}</loc><lastmod>{iso}</lastmod>'
                     f'<changefreq>weekly</changefreq><priority>0.6</priority></url>')
    parts.append('</urlset>')
    return "\n".join(parts)

def main():
    if not GROQ_API_KEY:
        print("Ошибка: Не найден ключ GROQ_API_KEY")
        return

    os.makedirs(NEWS_DIR, exist_ok=True)

    print("Загружаем существующие новости...")
    existing_news = load_existing_news()
    existing_links = {item['link'] for item in existing_news}

    # Присваиваем slug старым новостям
    for n in existing_news:
        if not n.get('slug'):
            n['slug'] = make_slug(n['title'])

    # Перегенерируем HTML всех существующих страниц
    print("Обновляем страницы существующих новостей...")
    for n in existing_news:
        path = os.path.join(NEWS_DIR, n['slug'] + '.html')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(render_article_page(n))

    print("Собираем RSS...")
    rss_items = get_rss_news()
    new_count = 0

    for item in rss_items:
        if item['link'] in existing_links:
            continue
        if new_count >= MAX_NEWS_PER_RUN:
            break
        print(f"Обрабатываем: {item['title'][:50]}...")
        rewritten = rewrite_with_ai(item['title'], item['description'])
        if rewritten is None:
            continue
        entry = {
            "title": item['title'],
            "rewritten": rewritten,
            "link": item['link'],
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "slug": make_slug(item['title'])
        }
        while any(n['slug'] == entry['slug'] for n in existing_news):
            entry['slug'] += '-x'
        existing_news.insert(0, entry)
        existing_links.add(item['link'])
        new_count += 1
        path = os.path.join(NEWS_DIR, entry['slug'] + '.html')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(render_article_page(entry))

    print("Сохраняем news.json...")
    save_news(existing_news)

    print("Генерируем index.html...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(render_index(existing_news))

    print("Генерируем sitemap.xml...")
    with open(SITEMAP_FILE, "w", encoding="utf-8") as f:
        f.write(render_sitemap(existing_news))

    print(f"Готово! Добавлено {new_count} новостей. Всего: {len(existing_news)}")

if __name__ == "__main__":
    main()
