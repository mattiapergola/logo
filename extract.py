from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import os
import json
import re
from bs4 import BeautifulSoup
import time

def html_to_json(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    result = {}

    schedule_div = soup.find('div', id='schedule')
    if not schedule_div:
        print("AVVISO: Contenitore 'schedule' non trovato nel contenuto HTML!")
        return {}

    for day_div in schedule_div.find_all('div', class_='schedule__day'):
        day_title_tag = day_div.find('div', class_='schedule__dayTitle')
        if not day_title_tag:
            continue

        current_date = day_title_tag.text.strip()
        result[current_date] = {}

        for category_div in day_div.find_all('div', class_='schedule__category'):
            cat_header = category_div.find('div', class_='schedule__catHeader')
            if not cat_header:
                continue

            meta_div = cat_header.find('div', class_='card__meta')
            current_category = meta_div.text.strip() if meta_div else cat_header.get_text(" ", strip=True)
            result[current_date][current_category] = []

            category_body = category_div.find('div', class_='schedule__categoryBody')
            if not category_body:
                continue

            for event_div in category_body.find_all('div', class_='schedule__event'):
                event_header = event_div.find('div', class_='schedule__eventHeader')
                if not event_header:
                    continue

                time_span = event_header.find('span', class_='schedule__time')
                event_title_span = event_header.find('span', class_='schedule__eventTitle')

                event_data = {
                    "time": time_span.text.strip() if time_span else "",
                    "event": event_title_span.text.strip() if event_title_span else "Evento Sconosciuto",
                    "channels": []
                }

                channels_div = event_div.find('div', class_='schedule__channels')
                if channels_div:
                    for link in channels_div.find_all('a', href=re.compile(r'/watch\.php\?id=\d+')):
                        href = link.get('href', '')
                        channel_id_match = re.search(r'id=(\d+)', href)
                        if channel_id_match:
                            channel_id = channel_id_match.group(1)
                            channel_name = link.text.strip()
                            channel_name = re.sub(r'\s*CH-\d+$', '', channel_name).strip()

                            event_data["channels"].append({
                                "channel_name": channel_name,
                                "channel_id": channel_id
                            })

                result[current_date][current_category].append(event_data)

    return result

def modify_json_file(json_file_path):
    with open(json_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(json_file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print(f"File JSON modificato e salvato in {json_file_path}")

def extract_schedule_container(max_retries=3, retry_delay=5):
    initial_url = "https://dlhd.st/"

    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_output = os.path.join(script_dir, "daddyliveSchedule.json")

    print(f"Accesso alla pagina {initial_url} (seguendo eventuali redirect)...")

    for attempt in range(1, max_retries + 1):
        print(f"Tentativo {attempt} di {max_retries}...")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
                ignore_https_errors=True
            )
            page = context.new_page()

            try:
                print("Navigazione alla pagina...")
                response = page.goto(initial_url, timeout=60000, wait_until="domcontentloaded")

                final_url = page.url
                print(f"URL finale dopo redirect: {final_url}")

                print("Attesa per il caricamento completo...")
                page.wait_for_timeout(10000)

                schedule_content = page.evaluate("""() => {
                    const container = document.getElementById('schedule');
                    return container ? container.outerHTML : '';
                }""")

                if not schedule_content:
                    print("AVVISO: contenitore #schedule non trovato o vuoto!")

                    try:
                        html_debug = page.evaluate("() => document.documentElement.outerHTML")
                        with open("debug.html", "w", encoding="utf-8") as f:
                            f.write(html_debug)
                        print("HTML completo salvato in debug.html")
                    except Exception:
                        pass

                    if attempt < max_retries:
                        print(f"Attesa di {retry_delay} secondi prima del prossimo tentativo...")
                        browser.close()
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    return False

                print("Conversione HTML in formato JSON...")
                json_data = html_to_json(schedule_content)

                with open(json_output, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, indent=4, ensure_ascii=False)

                print(f"Dati JSON salvati in {json_output}")

                modify_json_file(json_output)
                browser.close()
                return True

            except PlaywrightTimeoutError as e:
                print(f"ERRORE DI TIMEOUT: {str(e)}")
                try:
                    page.screenshot(path=f"error_screenshot_attempt_{attempt}.png")
                    print(f"Screenshot dell'errore salvato in error_screenshot_attempt_{attempt}.png")
                except Exception:
                    pass

                browser.close()

                if attempt < max_retries:
                    print(f"Attesa di {retry_delay} secondi prima del prossimo tentativo...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    print(f"Tutti i {max_retries} tentativi falliti.")
                    return False

            except Exception as e:
                print(f"ERRORE: {str(e)}")
                try:
                    page.screenshot(path=f"error_screenshot_attempt_{attempt}.png")
                    print(f"Screenshot dell'errore salvato in error_screenshot_attempt_{attempt}.png")
                except Exception:
                    pass

                browser.close()

                if attempt < max_retries:
                    print(f"Attesa di {retry_delay} secondi prima del prossimo tentativo...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    print(f"Tutti i {max_retries} tentativi falliti.")
                    return False

    return False

if __name__ == "__main__":
    success = extract_schedule_container()
    if not success:
        print("Errore durante l'estrazione dello schedule da dlhd.")
        exit(1)