import os
import re
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# === НАСТРОЙКИ ===
RSS_URL = "https://lenta.ru/rss/news"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
OUTPUT_FILE = "index.html"
NEWS_JSON = "news.json"
MAX_NEWS_PER_RUN = 3
MAX_TOTAL_NEWS = 50
MODEL_NAME = "openai/gpt-oss-120b"

# Расширенный список маркеров "мусорного" ответа
BAD_PATTERNS = [
    "пришлите",
    "предоставьте",
    "предоставлен",
    "укажите текст",
    "не могу переписать",
    "переписать её невозможно",
    "переписать невозможно",
    "нужен текст",
    "я не могу",
    "извините",
    "прошу прощения",
    "не имею доступа",
    "текст не предоставлен",
    "текст новости не",
    "невозможно",
    "не предоставлен"
]

def load_existing_news():
    if os.path.exists(NEWS_JSON):
        with open(NEWS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_news(news_list):
    with open(NEWS_JSON, "w", encoding="utf-8") as f:
        json.dump(news_list, f, ensure_ascii=False, indent=2)

def get_rss_news():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(RSS_URL, headers=headers, timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items = root.findall(".//item")
    news = []
    for item in items:
        title = item.find("title").text
        description = item.find("description").text
        link = item.find("link").text
        pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
        news.append({
            "title": title,
            "description": description,
            "link": link,
            "pub_date": pub_date
        })
    return news

def clean_text(text):
    """Убирает markdown-обёртки, которые ИИ добавляет от себя."""
    text = re.sub(r"\*\*Заголовок:\*\*\s*", "", text)
    text = re.sub(r"\*\*Текст:\*\*\s*", "", text)
    text = re.sub(r"\*\*", "", text)
    text = text.strip()
    return text

def is_bad_response(text):
    """Проверяет, является ли ответ ИИ мусорным."""
    if not text or len(text) < 50:
        return True
    text_lower = text.lower()
    return any(pattern in text_lower for pattern in BAD_PATTERNS)

def rewrite_with_ai(title, description):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": "Ты — опытный редактор новостного издания. Ты переписываешь новости своими словами на русском языке: сохраняешь все ключевые факты, но меняешь структуру предложений и лексику. Отвечай ТОЛЬКО готовым текстом новости — без приветствий, пояснений, вопросов, без пометок 'Заголовок:' и 'Текст:', без markdown."
            },
            {
                "role": "user",
                "content": f"Перепиши эту новость:\n\nЗаголовок: {title}\n\nТекст: {description}"
            }
        ],
        "temperature": 0.7
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        if response.status_code == 200:
            result = response.json()
            text = result['choices'][0]['message']['content'].strip()
            text = clean_text(text)
            if is_bad_response(text):
                print(f"  → ИИ вернул мусор, пропускаем новость")
                return None
            return text
        else:
            print(f"  → Ошибка ИИ: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"  → Ошибка при запросе к ИИ: {e}")
        return None

def generate_html(news_list):
    html = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Актуальные новости России и мира. Автоматическое обновление каждый час.">
    <title>Новости дня</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f0f2f5; color: #333; }
        header { background: #1a1a2e; color: white; padding: 20px; border-radius: 12px; margin-bottom: 24px; text-align: center; }
        header h1 { margin: 0; font-size: 28px; }
        .news-item { background: white; padding: 24px; margin-bottom: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); transition: box-shadow 0.2s; }
        .news-item:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.12); }
        .news-item h2 { color: #1a1a2e; margin-top: 0; font-size: 20px; line-height: 1.4; }
        .news-item p { line-height: 1.7; color: #444; }
        .source { font-size: 13px; color: #888; margin-top: 12px; padding-top: 12px; border-top: 1px solid #eee; }
        .source a { color: #0066cc; text-decoration: none; }
        .date { font-size: 12px; color: #aaa; margin-top: 4px; }
    </style>
</head>
<body>
    <header><h1>Новости дня</h1></header>
"""
    for news in news_list:
        html += f"""
    <div class="news-item">
        <h2>{news['title']}</h2>
        <p>{news['rewritten']}</p>
        <div class="source">Источник: <a href="{news['link']}" target="_blank" rel="noopener">Lenta.ru</a></div>
        <div class="date">{news.get('date', '')}</div>
    </div>
"""
    html += """
</body>
</html>"""
    return html

def main():
    if not GROQ_API_KEY:
        print("Ошибка: Не найден ключ GROQ_API_KEY")
        return

    print("Загружаем существующие новости...")
    existing_news = load_existing_news()
    existing_links = {item['link'] for item in existing_news}

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
        existing_news.insert(0, {
            "title": item['title'],
            "rewritten": rewritten,
            "link": item['link'],
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        })
        new_count += 1

    existing_news = existing_news[:MAX_TOTAL_NEWS]

    print("Сохраняем news.json...")
    save_news(existing_news)

    print("Генерируем HTML...")
    html = generate_html(existing_news)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Готово! Добавлено {new_count} новостей. Всего на сайте: {len(existing_news)}")

if __name__ == "__main__":
    main()
