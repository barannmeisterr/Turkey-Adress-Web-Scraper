import requests
import pymysql

API_URL = "https://cbsapi.tkgm.gov.tr/megsiswebapi.v3.1/api/maksIdariYapi/illiste"

db = pymysql.connect(
    host="localhost",
    port=3307,
    user="sail",
    password="password",
    database="adres_data",
    charset="utf8mb4",
    autocommit=True
)
cur = db.cursor()

resp = requests.get(API_URL, timeout=30)
resp.raise_for_status()
data = resp.json()

sql = """
INSERT INTO iller (id, name)
VALUES (%s, %s)
ON DUPLICATE KEY UPDATE
    name = VALUES(name)
"""

count = 0

for feature in data.get("features", []):
    props = feature.get("properties", {})

    il_id = props.get("id", "").strip("{}")
    il_name = props.get("text", "").strip()

    if not il_id or not il_name:
        continue

    cur.execute(sql, (il_id, il_name))
    count += 1

print(f"{count} adet il iller tablosuna yazıldı.")
