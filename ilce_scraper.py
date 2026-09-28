import requests
import pymysql
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

ILCE_URL_TEMPLATE = (
    "https://cbsapi.tkgm.gov.tr/megsiswebapi.v3.1/api//"
    "maksIdariYapi/ilceliste/%7B{il_id}%7D"
)

SLEEP_SECONDS = 0.3

# =========================
# DB
# =========================
def get_db():
    return pymysql.connect(**DB_CONFIG)

# =========================
# SQL
# =========================
SQL_GET_ILLER = """
SELECT id, name
FROM iller
ORDER BY name
"""

SQL_INSERT_ILCE = """
INSERT INTO ilceler (id, name, il_id)
VALUES (%s, %s, %s)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    il_id = VALUES(il_id)
"""

# =========================
# API
# =========================
def fetch_ilceler(session, il_id):
    url = ILCE_URL_TEMPLATE.format(il_id=il_id)
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

# =========================
# MAIN
# =========================
def sync_ilceler():
    db = get_db()
    cursor = db.cursor(pymysql.cursors.DictCursor)

    # ---- illeri al
    cursor.execute(SQL_GET_ILLER)
    iller = cursor.fetchall()

    print(f"🔎 {len(iller)} il bulundu.")

    session = requests.Session()
    total_ilce = 0

    for il in iller:
        il_id = il["id"]
        il_name = il["name"]

        print(f"\n➡️ {il_name} ilçeleri çekiliyor...")

        try:
            data = fetch_ilceler(session, il_id)
        except Exception as e:
            print(f"❌ API hatası ({il_name}): {e}")
            continue

        count = 0

        for feature in data.get("features", []):
            props = feature.get("properties", {})

            ilce_id = props.get("id", "").strip("{}")
            ilce_name = props.get("text", "").strip()

            if not ilce_id or not ilce_name:
                continue

            cursor.execute(
                SQL_INSERT_ILCE,
                (ilce_id, ilce_name, il_id)
            )
            count += 1

        total_ilce += count
        print(f"   ✔️ {count} ilçe eklendi.")

        time.sleep(SLEEP_SECONDS)

    cursor.close()
    db.close()

    print(f"\n✅ İşlem tamamlandı. Toplam {total_ilce} ilçe işlendi.")

# =========================
# ENTRY
# =========================
if __name__ == "__main__":
    sync_ilceler()

