import requests
import pymysql
import json
import time

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
SQL_GET_FIX_ILCELER = """
SELECT DISTINCT ilce_id
FROM mahalleler
WHERE coordinates IS NULL
ORDER BY ilce_id
"""

SQL_UPDATE_MAHALLE = """
UPDATE mahalleler
SET coordinates = %s,
    geo_type = %s
WHERE id = %s
  AND coordinates IS NULL
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
def fix_null_coordinates():
    db = get_db()
    cursor = db.cursor(pymysql.cursors.DictCursor)

    # --- DÜZELTİLECEK İLÇELER
    cursor.execute(SQL_GET_FIX_ILCELER)
    fix_ilceler = [r["ilce_id"] for r in cursor.fetchall()]

    if not fix_ilceler:
        print("✅ NULL coordinates olan mahalle yok.")
        cursor.close()
        db.close()
        return

    print(f"🏘️ {len(fix_ilceler)} ilçe düzeltilecek.")

    session = requests.Session()
    fixed_count = 0

    for ilce_id in fix_ilceler:
        print(f"\n➡️ İlçe işleniyor: {ilce_id}")

        try:
            data = fetch_mahalleler(session, ilce_id)
        except Exception as e:
            print(f"❌ API HATASI ({ilce_id}): {e}")
            print("⛔ Script durdu. Tekrar çalıştırarak devam edebilirsin.")
            break

        for feature in data.get("features", []):
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})

            mahalle_id = props.get("id", "").strip("{}")
            if not mahalle_id:
                continue

            geo_type = geom.get("type")
            coordinates = geom.get("coordinates")

            if geo_type is None or coordinates is None:
                continue

            cursor.execute(
                SQL_UPDATE_MAHALLE,
                (
                    json.dumps(coordinates, ensure_ascii=False),
                    geo_type,
                    mahalle_id
                )
            )
            fixed_count += cursor.rowcount

        time.sleep(SLEEP_SECONDS)

    cursor.close()
    db.close()

    print(f"\n✅ Düzeltme tamamlandı. Toplam {fixed_count} mahalle güncellendi.")

# =========================
# ENTRY
# =========================
if __name__ == "__main__":
    fix_null_coordinates()
