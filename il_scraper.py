
import os
import json
import uuid
import requests
import psycopg
from psycopg.types.json import Jsonb

# PostgreSQL bağlantısı
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "wisp_planner",
    "user": "postgres",
    "password": "arda"
}

API_URL = (
    "https://cbsapi.tkgm.gov.tr/"
    "megsiswebapi.v3.1/api/"
    "maksIdariYapi/illiste"
)

ANTALYA_ID = uuid.UUID(
    "C9F49F91-EC26-4570-9C23-B5A431FD12C6"
)

def fetch_antalya():
    response = requests.get(API_URL, timeout=30)
    response.raise_for_status()

    data = response.json()

    for feature in data.get("features", []):
        props = feature.get("properties") or {}

        raw_id = props.get("id")
        if not raw_id:
            continue

        il_id = uuid.UUID(raw_id.strip("{}"))

        if il_id != ANTALYA_ID:
            continue

        return feature

    raise ValueError(
        "Antalya API yanıtında bulunamadı."
    )


def save_antalya(feature):
    props = feature["properties"]
    geometry = feature.get("geometry")

    sql = """
        INSERT INTO iller (
            id,
            name,
            geometry,
            properties,
            raw_geometry
        )
        VALUES (
            %s,
            %s,
            CASE
                WHEN %s::text IS NULL THEN NULL
                ELSE ST_SetSRID(
                    ST_GeomFromGeoJSON(%s),
                    4326
                )
            END,
            %s,
            %s
        )
        ON CONFLICT (id)
        DO UPDATE SET
            name = EXCLUDED.name,
            geometry = EXCLUDED.geometry,
            properties = EXCLUDED.properties,
            raw_geometry = EXCLUDED.raw_geometry
    """

    geometry_json = (
        json.dumps(geometry, ensure_ascii=False)
        if geometry is not None
        else None
    )

    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    ANTALYA_ID,
                    props["text"].strip(),
                    geometry_json,
                    geometry_json,
                    Jsonb(props),
                    Jsonb(geometry)
                )
            )

    print("Antalya PostgreSQL'e kaydedildi.")


if __name__ == "__main__":
    antalya = fetch_antalya()
    save_antalya(antalya)
