import os
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# Настройки
RSS_URL = "https://lenta.ru/rss/news"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
OUTPUT_FILE = "index.html"
NEWS_JSON = "news.json"
MAX_NEWS_PER_RUN = 3  # Сколько новостей обрабатывать за один запуск (чтобы не перегружать ИИ)
MAX_TOTAL_NEWS = 50   # Максимум новостей на сайте

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
    response = requests.get(RSS_URL, headers=headers)
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

def rewrite_with_ai(title, description):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    prompt = f"Ты — опытный редактор новостного издания. Перепиши следующую новость своими словами, сохранив все ключевые факты, но изменив структуру предложений и лексику. Сделай текст уникальным и интересным для читателя. Верни только готовый текст. Заголовок: {title}. Текст: {description}"
    data = {
        "model": "llama3-8b-8192",
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            print(f"Ошибка ИИ: {response.status_code} - {response.text}")
            return description
    except Exception as e:
        print(f"Ошибка при запросе к ИИ: {e}")
        return description

def generate_html(news_list):
    html = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Автоматические новости</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f4f4f4; }
        .news-item { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; }
        h2 { color: #0066cc; margin-top: 0; }
        .source { font-size: 0.8em; color: #888; margin-top: 10px; }
        .date { font-size: 0.8em; color: #aaa; }
    </style>
</head>
<body>
    <h1>Новости дня</h1>
"""
    for news in news_list:
        html += f"""
    <div class="news-item">
        <h2>{news['title']}</h2>
        <p>{news['rewritten']}</p>
        <div class="source">Источник: <a href="{news['link']}" target="_blank">Lenta.ru</a></div>
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
        existing_news.insert(0, {
            "title": item['title'],
            "rewritten": rewritten,
            "link": item['link'],
            "date": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        new_count += 1

    # Ограничиваем общее количество
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
