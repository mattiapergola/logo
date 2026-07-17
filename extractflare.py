import requests
import os
import json
from datetime import datetime
import re
from bs4 import BeautifulSoup

# ==========================================
# Configurazione
# ==========================================
DLHD_BASE = "https://dlhd.st/"
DLHD_247_URL = DLHD_BASE + "24-7-channels.php"
OUTPUT_247_HTML = "247.html"
OUTPUT_SCHEDULE_JSON = "daddyliveSchedule.json"
RETRIES = int(os.getenv("DLHD_RETRIES", "3"))
# FlareSolverr per bypassare Cloudflare
FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL")
# anna.mosene@gmail.com su huggingface
# ==========================================
# Parsing schedule -> JSON
# ==========================================

def html_to_json(html_content):
    """Converte il contenuto HTML della programmazione in formato JSON organizzato per giorno / categoria / eventi."""
    soup = BeautifulSoup(html_content, 'html.parser')
    result = {}

    # ATTENZIONE MANUTENZIONE:
    # La prima versione di questo script aveva la regex dei link canale scritta come r'/watch\\.php\\?id=\\d+'.
    # Essendo una raw string con backslash doppi, il pattern realizzato cercava letteralmente le sequenze "\\." e "\\?"
    # e NON trovava i link reali "/watch.php?id=123" -> risultato: channels[] sempre vuoto.
    # Ora il pattern corretto (usato più sotto) è r'/watch\.php\?id=\d+' (singolo livello di escape) così i channel_id vengono estratti.
    # Se in futuro cambia la struttura degli href (es. query string diversa), aggiornare di conseguenza.

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
            current_category = cat_header.text.strip()
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
                    # NOTE: la regex precedente era doppiamente escape (r'/watch\\.php\\?id=\\d+') e non matchava l'href reale.
                    # Corretto pattern: /watch\.php?id=123  (usando raw string singolo livello)
                    for link in channels_div.find_all('a', href=re.compile(r'/watch\.php\?id=\d+')):
                        href = link.get('href', '')
                        channel_id_match = re.search(r'id=(\d+)', href)
                        if channel_id_match:
                            channel_id = channel_id_match.group(1)
                            channel_name = link.text.strip()
                            channel_name = re.sub(r'\\s*CH-\\d+$', '', channel_name).strip()
                            event_data["channels"].append({
                                "channel_name": channel_name,
                                "channel_id": channel_id
                            })
                result[current_date][current_category].append(event_data)
    return result


def modify_json_file(json_file_path):
    with open(json_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Se servissero modifiche future alle chiavi data si possono inserire qui
    with open(json_file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    print(f"File JSON normalizzato salvato in {json_file_path}")

# ==========================================
# FlareSolverr
# ==========================================

def fetch_with_flaresolverr(url, max_timeout=60000):
    """Usa FlareSolverr per bypassare Cloudflare e ottenere l'HTML."""
    print(f"[FLARE] Richiesta a FlareSolverr per: {url}")
    
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": max_timeout
    }
    
    try:
        response = requests.post(FLARESOLVERR_URL, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") == "ok":
            solution = data.get("solution", {})
            html_content = solution.get("response")
            print(f"[FLARE] ✓ Successo! HTML ricevuto ({len(html_content)} bytes)")
            return html_content
        else:
            print(f"[FLARE] ✗ Errore: {data.get('message', 'Unknown error')}")
            return None
    except Exception as e:
        print(f"[FLARE] ✗ Eccezione: {e}")
        return None


def fetch_247_channels_html():
    """Usa FlareSolverr per scaricare la pagina dei canali 24/7."""
    print(f"[24/7] Download pagina: {DLHD_247_URL}")
    
    for attempt in range(1, RETRIES + 1):
        try:
            print(f"[24/7] Tentativo {attempt}/{RETRIES}...")
            html_content = fetch_with_flaresolverr(DLHD_247_URL)
            
            if not html_content or len(html_content) < 500:
                raise ValueError(f"Contenuto troppo corto: {len(html_content) if html_content else 0} bytes")
            
            with open(OUTPUT_247_HTML, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"[24/7] Salvato HTML in {OUTPUT_247_HTML} ({len(html_content)} bytes)")
            return True
            
        except Exception as e:
            print(f"[24/7] Errore tentativo {attempt}: {e}")
            if attempt < RETRIES:
                print("[24/7] Retry...")
    
    print(f"[24/7] FALLITO definitivamente")
    return False


def extract_schedule_container():
    """Usa FlareSolverr per ottenere lo schedule dalla homepage."""
    url = DLHD_BASE
    print(f"[SCHEDULE] Accesso alla pagina {url} tramite FlareSolverr...")
    
    for attempt in range(1, RETRIES + 1):
        try:
            print(f"[SCHEDULE] Tentativo {attempt}/{RETRIES}...")
            schedule_content = fetch_with_flaresolverr(url)
            
            if not schedule_content or len(schedule_content) < 1000:
                raise ValueError(f"HTML troppo corto: {len(schedule_content) if schedule_content else 0} bytes")
            
            print("[SCHEDULE] Conversione HTML -> JSON...")
            json_data = html_to_json(schedule_content)
            with open(OUTPUT_SCHEDULE_JSON, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=4)
            print(f"[SCHEDULE] Salvato JSON in {OUTPUT_SCHEDULE_JSON}")
            modify_json_file(OUTPUT_SCHEDULE_JSON)
            return True
            
        except Exception as e:
            print(f"[SCHEDULE] Errore tentativo {attempt}: {e}")
            if attempt < RETRIES:
                print("[SCHEDULE] Retry...")
    
    print(f"[SCHEDULE] FALLITO definitivamente")
    return False

# ==========================================
# Main
# ==========================================
if __name__ == "__main__":
    ok_schedule = extract_schedule_container()
    ok_247 = fetch_247_channels_html()
    if not ok_schedule:
        print("AVVISO: schedule NON scaricato correttamente.")
    if not ok_247:
        print("AVVISO: 24/7 page NON scaricata correttamente.")
    if ok_schedule and ok_247:
        print("Completato senza errori critici.")
