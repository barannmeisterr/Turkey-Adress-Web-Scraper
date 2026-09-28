import requests
import pymysql
import time
import json

# =========================
# CONFIG
# =========================
DB_CONFIG = {
    "host": "localhost",
    "port": 3307,
    "user": "sail",
    "password": "password",
    "database": "adres_data",
    "charset": "utf8mb4",
    "autocommit": True
}

MAHALLE_URL_TEMPLATE = (
    "https://cbsapi.tkgm.gov.tr/megsiswebapi.v3.1/api//"
    "maksIdariYapi/mahalleliste/%7B{ilce_id}%7D"
)

SLEEP_SECONDS = 3

# =========================
# DB
# =========================
def get_db():
    return pymysql.connect(**DB_CONFIG)

# =========================
# SQL
# =========================
SQL_GET_ILCELER = """
SELECT id, name, il_id
FROM ilceler
ORDER BY name
"""

SQL_INSERT_MAHALLE = """
INSERT INTO mahalleler (id, name, ilce_id, polygon)
VALUES (%s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    ilce_id = VALUES(ilce_id),
    polygon = VALUES(polygon)
"""

SQL_GET_STATE = """
SELECT last_id
FROM scraper_state
WHERE name = 'mahalle'
"""

SQL_UPDATE_STATE = """
UPDATE scraper_state
SET last_id = %s
WHERE name = 'mahalle'
"""

# =========================
# API
# =========================
def fetch_mahalleler(session, ilce_id):
    url = MAHALLE_URL_TEMPLATE.format(ilce_id=ilce_id)
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

# =========================
# MAIN
# =========================
def sync_mahalleler():
    db = get_db()
    cursor = db.cursor(pymysql.cursors.DictCursor)

    # ---- STATE OKU
    cursor.execute(SQL_GET_STATE)
    row = cursor.fetchone()
    last_processed_ilce = row["last_id"] if row else None

    skip = last_processed_ilce is not None

    if last_processed_ilce:
        print(f"⏩ Kaldığı yerden devam edilecek. Son ilçe ID: {last_processed_ilce}")
    else:
        print("▶️ İlk çalıştırma, baştan başlıyor.")

    # ---- İLÇELERİ AL
    cursor.execute(SQL_GET_ILCELER)
    ilceler = cursor.fetchall()

    print(f"🔎 {len(ilceler)} ilçe bulundu.")

    session = requests.Session()
    total_mahalle = 0

    for ilce in ilceler:
        ilce_id = ilce["id"]
        ilce_name = ilce["name"]

        # ---- RESUME (İLÇE BAZLI)
        if skip:
            if ilce_id != last_processed_ilce:
                continue
            skip = False  # bu ilçe yeniden işlenecek

        print(f"\n➡️ {ilce_name} mahalleleri çekiliyor...")

        try:
            data = fetch_mahalleler(session, ilce_id)
        except Exception as e:
            print(f"❌ API HATASI ({ilce_name}): {e}")
            print("⛔ Script durdu. Bir sonraki çalıştırmada buradan devam eder.")
            break

        count = 0

        for feature in data.get("features", []):
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})

            mahalle_id = props.get("id", "").strip("{}")
            mahalle_name = props.get("text", "").strip()

            if not mahalle_id or not mahalle_name:
                continue

            polygon_text = None

            if geom.get("type") == "Polygon":
                coords = geom.get("coordinates", [])
                if coords and len(coords) > 0:
                    # SADECE dış ring
                    polygon_text = json.dumps(coords[0], ensure_ascii=False)

            cursor.execute(
                SQL_INSERT_MAHALLE,
                (mahalle_id, mahalle_name, ilce_id, polygon_text)
            )
            count += 1

        total_mahalle += count
        print(f"   ✔️ {count} mahalle eklendi.")

        # ---- İLÇE TAMAM → STATE GÜNCELLE
        cursor.execute(SQL_UPDATE_STATE, (ilce_id,))

        time.sleep(SLEEP_SECONDS)

    cursor.close()
    db.close()

    print(f"\n✅ İşlem tamamlandı. Toplam {total_mahalle} mahalle işlendi.")

# =========================
# ENTRY
# =========================
if __name__ == "__main__":
    sync_mahalleler()
