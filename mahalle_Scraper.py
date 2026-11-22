
import os
import json
import uuid
import time

import requests
import psycopg

from psycopg.types.json import Jsonb
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ==========================================
# 1. POSTGRESQL BAĞLANTISI
# ==========================================

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "wisp_planner",
    "user": "postgres",
    "password": "arda"
}


# ==========================================
# 2. API AYARLARI
# ==========================================

ANTALYA_ID = uuid.UUID(
    "C9F49F91-EC26-4570-9C23-B5A431FD12C6"
)

BASE_URL = (
    "https://cbsapi.tkgm.gov.tr/"
    "megsiswebapi.v3.1/api/maksIdariYapi/"
    "mahalleliste"
)

REQUEST_DELAY = 1.0


# ==========================================
# 3. HTTP SESSION
# ==========================================

def create_session():

    session = requests.Session()

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
        status_forcelist=[
            429, 500, 502, 503, 504
        ],
        allowed_methods=["GET"]
    )

    adapter = HTTPAdapter(max_retries=retry)

    session.mount("https://", adapter)

    session.headers.update({
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    })

    return session


# ==========================================
# 4. ANTALYA İLÇELERİNİ VERİTABANINDAN OKU
# ==========================================

def get_ilceler(conn):

    sql = """
        SELECT id, name
        FROM ilceler
        WHERE il_id = %s
        ORDER BY name
    """

    with conn.cursor() as cur:
        cur.execute(sql, (ANTALYA_ID,))
        return cur.fetchall()


# ==========================================
# 5. İLÇENİN MAHALLELERİNİ API'DEN ÇEK
# ==========================================

def fetch_mahalleler(session, ilce_id, ilce_name):

    # UUID'yi API'deki gibi büyük harfe çevir.
    uuid_text = str(ilce_id).upper()

    # %7B ve %7D, { ve } karakterleridir.
    url = f"{BASE_URL}/%7B{uuid_text}%7D"

    print(f"\nİlçe: {ilce_name}")
    print(f"API: {url}")

    response = session.get(
        url,
        timeout=60
    )

    print("HTTP durum:", response.status_code)

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict):
        raise ValueError(
            f"{ilce_name}: JSON nesnesi bekleniyordu."
        )

    features = data.get("features")

    if not isinstance(features, list):
        raise ValueError(
            f"{ilce_name}: features listesi bulunamadı."
        )

    if not features:
        raise ValueError(
            f"{ilce_name}: API boş features döndürdü. "
            f"Yanıt: {response.text[:300]}"
        )

    print(f"Bulunan mahalle: {len(features)}")

    return features


# ==========================================
# 6. MAHALLELERİ POSTGRESQL'E KAYDET
# ==========================================

def save_mahalleler(conn, ilce_id, features):

    sql = """
        INSERT INTO mahalleler (
            id,
            name,
            ilce_id,
            geometry,
            properties,
            raw_geometry
        )
        VALUES (
            %s,
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
            ilce_id = EXCLUDED.ilce_id,
            geometry = EXCLUDED.geometry,
            properties = EXCLUDED.properties,
            raw_geometry = EXCLUDED.raw_geometry
    """

    saved_count = 0

    with conn.cursor() as cur:

        for feature in features:

            props = feature.get("properties") or {}
            geometry = feature.get("geometry")

            raw_id = props.get("id")
            raw_name = props.get("text")

            if not raw_id or not raw_name:
                raise ValueError(
                    f"Geçersiz mahalle kaydı: {props}"
                )

            mahalle_id = uuid.UUID(
                str(raw_id).strip("{}")
            )

            mahalle_name = str(raw_name).strip()

            geometry_json = (
                json.dumps(
                    geometry,
                    ensure_ascii=False
                )
                if geometry is not None
                else None
            )

            cur.execute(
                sql,
                (
                    mahalle_id,
                    mahalle_name,
                    ilce_id,
                    geometry_json,
                    geometry_json,
                    Jsonb(props),
                    Jsonb(geometry)
                )
            )

            saved_count += 1

    return saved_count


# ==========================================
# 7. SCRAPER'I ÇALIŞTIR
# ==========================================

def main():

    print("=" * 55)
    print("ANTALYA MAHALLE SCRAPER")
    print("=" * 55)

    session = create_session()

    total_saved = 0
    successful_districts = 0
    failed_districts = []

    try:
        with psycopg.connect(**DB_CONFIG) as conn:

            ilceler = get_ilceler(conn)

            print(
                f"\nVeritabanındaki ilçe sayısı: "
                f"{len(ilceler)}"
            )

            if not ilceler:
                raise ValueError(
                    "Antalya ilçeleri bulunamadı. "
                    "Önce ilce_scraper.py çalıştır."
                )

            for index, (ilce_id, ilce_name) in enumerate(
                ilceler,
                start=1
            ):

                print(
                    f"\n[{index}/{len(ilceler)}] "
                    f"{ilce_name} işleniyor..."
                )

                try:
                    features = fetch_mahalleler(
                        session,
                        ilce_id,
                        ilce_name
                    )

                    # Her ilçeyi ayrı transaction
                    # olarak kaydediyoruz.
                    with conn.transaction():
                        count = save_mahalleler(
                            conn,
                            ilce_id,
                            features
                        )

                    total_saved += count
                    successful_districts += 1

                    print(
                        f"Kaydedildi: {ilce_name} "
                        f"({count} mahalle)"
                    )

                except (
                    requests.RequestException,
                    ValueError,
                    KeyError,
                    psycopg.Error
                ) as exc:

                    failed_districts.append(
                        (ilce_name, str(exc))
                    )

                    print(
                        f"HATA: {ilce_name} - {exc}"
                    )

                time.sleep(REQUEST_DELAY)

    finally:
        session.close()

    print("\n" + "=" * 55)
    print("SCRAPER RAPORU")
    print("=" * 55)

    print("Başarılı ilçe:", successful_districts)
    print("Hatalı ilçe:", len(failed_districts))
    print("İşlenen mahalle kaydı:", total_saved)

    if failed_districts:
        print("\nBaşarısız ilçeler:")

        for name, error in failed_districts:
            print(f"- {name}: {error}")

        raise RuntimeError(
            "Bazı ilçelerin mahalleleri alınamadı. "
            "Hataları giderip scraper'ı tekrar çalıştır."
        )

    print("\nTüm ilçeler başarıyla işlendi.")


if __name__ == "__main__":
    main()
