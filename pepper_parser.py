import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime
import pytz
import re # Для более точного поиска картинок
import os # Импортируем модуль os для работы с файловой системой

# --- Настройки ScraperAPI ---
API_KEY = os.environ.get("SCRAPERAPI_API_KEY") # <-- Вставьте сюда ваш API-ключ с ScraperAPI.com
SCRAPERAPI_URL = "http://api.scraperapi.com/"
TARGET_URL = "https://www.pepper.ru/new"

# Параметры запроса для ScraperAPI
scraperapi_params = {
    'api_key': API_KEY,
    'url': TARGET_URL,
    'country_code': 'ru',
    'render': 'true',
    'session_number': '123' # Пример использования сессии (для поддержания одного IP на время сессии)
                            # Удалите, если не нужно или не хотите использовать сессии
}

base_url = "https://www.pepper.ru"
entries = []
fg = None # Инициализируем fg как None, чтобы избежать NameError, если создание fg будет пропущено

try:
    print(f"Отправка запроса через ScraperAPI к: {TARGET_URL}")
    # Увеличен таймаут до 180 секунд (3 минуты)
    response = requests.get(SCRAPERAPI_URL, params=scraperapi_params, timeout=180) 

    if response.status_code == 200:
        html_content = response.text
        print(f"✅ Страница успешно загружена через ScraperAPI. Длина контента: {len(html_content)}")

        # Парсинг HTML с помощью BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        all_found_cards = []

        # --- Путь 2: deals-list -> article ---
        # Ищем контейнер deals-list
        deals_list_container = soup.find('div', class_='deals-list')
        if deals_list_container:
            print("✅ 'deals-list' найден.")
            # Ищем элементы article ВНУТРИ deals-list
            articles_in_deals_list = deals_list_container.find_all('article')
            if articles_in_deals_list:
                print(f"✅ Найдено {len(articles_in_deals_list)} элементов 'article' внутри 'deals-list'.")
                all_found_cards.extend(articles_in_deals_list)
            else:
                print("❌ Элементы 'article' не найдены внутри 'deals-list'.")
        else:
            print("❌ 'deals-list' не найден. Список предложений будет пустым.")

        # Теперь offer_cards - это all_found_cards. Если ничего не найдено, offer_cards будет пустым.
        offer_cards = all_found_cards
        if not offer_cards:
            print("❌ Контейнер 'deals-list' или его элементы 'article' не найдены. Список предложений будет пустым.")


        print("🔍 Найденные скидки:")

        # Добавляем нумерацию при парсинге
        for i, card in enumerate(offer_cards): # Используем enumerate для получения индекса
            # Определяем, является ли "card" уже тегом <a> (если это из резервного поиска),
            # или нужно искать <a> внутри других контейнеров (swiper-slide, article)
            offer_link_tag = card.find('a', href=re.compile(r'^/deals/')) if card.name != 'a' else card
            
            if not offer_link_tag:
                continue # Пропускаем, если не нашли ссылку на сделку

            href = offer_link_tag.get('href')
            title = offer_link_tag.get_text(strip=True)
            image_url = None

            # Поиск изображения внутри текущего элемента карточки (card)
            img_tag = card.find('img', src=True)
            
            if img_tag:
                potential_image_url = img_tag['src']
                # Проверяем, содержит ли URL "cdn"
                if potential_image_url and "cdn" in potential_image_url:
                    image_url = potential_image_url
                    # Обработка относительных URL
                    if image_url: # Проверка, что image_url не пустой после фильтрации
                        if image_url.startswith('//'):
                            image_url = 'https:' + image_url
                        elif image_url.startswith('/'):
                            image_url = base_url + image_url

            if title:
                full_link = base_url + href
                print(f"📌 {i+1}. Название: {title}") # Выводим номер элемента
                print(f"🔗 Ссылка:   {full_link}")
                if image_url:
                    print(f"🖼️ Изображение: {image_url}")
                print()

                entries.append({
                    'title': title,
                    'link': full_link,
                    'image': image_url,
                    'index': i + 1 # Добавляем индекс в запись
                })

        # Удаление дубликатов (ключ - ссылка, чтобы избежать дублирования одной и той же сделки)
        # Порядок сохраняется за счет логики с ordered_unique_entries
        ordered_unique_entries = []
        seen_links = set()
        for entry in entries:
            if entry['link'] not in seen_links:
                ordered_unique_entries.append(entry)
                seen_links.add(entry['link'])
        
        # Теперь уникальные записи в нужном порядке
        unique_entries = ordered_unique_entries

        # RSS
        fg = FeedGenerator() # fg определяется здесь
        fg.id(TARGET_URL)
        fg.title('Скидки с Pepper.ru')
        fg.link(href=TARGET_URL, rel='alternate')
        fg.description('Новые скидки с сайта Pepper.ru')
        fg.language('ru')

        # Общая секция <image> для канала RSS удалена

        timezone = pytz.timezone('Europe/Chisinau')

        # Итерируем по элементам в обратном порядке для RSS-фида
        for entry in reversed(unique_entries): # Изменение здесь: используем reversed()
            fe = fg.add_entry()
            fe.id(entry['link'])
            fe.title(f"[{entry['index']}] {entry['title']}") # Добавляем номер элемента в название
            fe.link(href=entry['link'])
            fe.pubDate(timezone.localize(datetime.now()))

            # --- Добавляем изображение для каждой записи (<item>) ---
            if entry['image']:
                # Вариант 1: Добавить изображение как HTML в описание (самый простой и широко поддерживаемый)
                fe.description(f'<img src="{entry["image"]}" /><br/>{entry["title"]}')

                # Вариант 2: Добавить изображение как enclosure (более "правильно" для RSS)
                # Требует определения MIME-типа изображения (например, 'image/jpeg', 'image/png')
                # и его длины. Если точная длина неизвестна, можно использовать 0 или 1.
                image_type = None
                if entry['image'].endswith(('.jpg', '.jpeg')):
                    image_type = 'image/jpeg'
                elif entry['image'].endswith('.png'):
                    image_type = 'image/png'
                elif entry['image'].endswith('.gif'):
                    image_type = 'image/gif'
                
                if image_type:
                    fe.enclosure(url=entry['image'], length='0', type=image_type)
                else:
                    print(f"Не удалось определить тип изображения для enclosure: {entry['image']}")

        # --- Сохранение RSS-фида ---
        rss_file = 'pepper_feed.xml'
        
        # Удаляем предыдущий файл, если он существует
        if os.path.exists(rss_file):
            try:
                os.remove(rss_file)
                print(f"✅ Предыдущий файл {rss_file} удален.")
            except OSError as e:
                print(f"❌ Ошибка при удалении файла {rss_file}: {e}")
        
        fg.rss_file(rss_file)
        print(f"\n✅ RSS-фид сохранён: {rss_file}")
    else:
        # Если статус код не 200, то fg не будет определен в этом блоке
        print(f"❌ Ошибка при загрузке страницы через ScraperAPI. Статус код: {response.status_code}")
        print(f"Текст ответа: {response.text[:500]}...")
        # Возвращаем ошибку для GitHub Actions
        raise Exception(f"Ошибка ScraperAPI: {response.status_code}")

except requests.exceptions.RequestException as req_e:
    print(f"Произошла ошибка при выполнении HTTP-запроса: {req_e}")
    # Возвращаем ошибку для GitHub Actions
    raise Exception(f"Ошибка HTTP-запроса: {req_e}")
except Exception as e:
    print(f"Произошла общая ошибка: {e}")
    # Возвращаем ошибку для GitHub Actions
    raise Exception(f"Общая ошибка: {e}")
