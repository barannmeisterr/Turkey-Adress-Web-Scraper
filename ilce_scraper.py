
import os
import json
import uuid

import requests
import psycopg
from psycopg.types.json import Jsonb


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
# 2. ANTALYA BİLGİLERİ
# ==========================================

ANTALYA_ID = uuid.UUID(
    "C9F49F91-EC26-4570-9C23-B5A431FD12C6"
)

# Tarayıcıdan aldığın URL'yi aynen kullanıyoruz.
API_URL = (
    "https://cbsapi.tkgm.gov.tr/"
    "megsiswebapi.v3.1/api/maksIdariYapi/"
    "ilceliste/%7BC9F49F91-EC26-4570-9C23-B5A431FD12C6%7D"
)


# ==========================================
# 3. API'DEN İLÇELERİ ÇEK
# ==========================================

def fetch_ilceler():

    print("=" * 55)
    print("ANTALYA İLÇE SCRAPER")
    print("=" * 55)

    print("\nAntalya ilçeleri API'den çekiliyor...")
    print("İstek URL:", API_URL)

    response = requests.get(
        API_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0"
        },
        timeout=60
    )

    print("\n--- API YANIT BİLGİLERİ ---")
    print("HTTP durum kodu:", response.status_code)
    print(
        "Content-Type:",
        response.headers.get("Content-Type")
    )

    print("\nYanıtın ilk 1000 karakteri:")
    print(response.text[:1000])

    response.raise_for_status()

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError(
            "API geçerli bir JSON yanıtı döndürmedi."
        ) from exc

    print("\n--- JSON ANALİZİ ---")
    print("JSON tipi:", type(data).__name__)

    if not isinstance(data, dict):
        raise ValueError(
            "Beklenmeyen JSON formatı. "
            "Bir JSON nesnesi bekleniyordu."
        )

    print("JSON anahtarları:", list(data.keys()))

    features = data.get("features")

    if not isinstance(features, list):
        raise ValueError(
            "API yanıtında features listesi bulunamadı."
        )

    print("Features sayısı:", len(features))

    if len(features) == 0:
        raise ValueError(
            "API 0 ilçe döndürdü. "
            "Veritabanına kayıt yapılmadı. "
            "Yukarıdaki API yanıtını kontrol et."
        )

    return features


# ==========================================
# 4. POSTGRESQL'E KAYDET
# ==========================================

def save_ilceler(features):

    sql = """
        INSERT INTO ilceler (
            id,
            name,
            il_id,
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
            il_id = EXCLUDED.il_id,
            geometry = EXCLUDED.geometry,
            properties = EXCLUDED.properties,
            raw_geometry = EXCLUDED.raw_geometry
    """

    saved_count = 0

    print("\nPostgreSQL bağlantısı kuruluyor...")

    with psycopg.connect(**DB_CONFIG) as conn:

        with conn.cursor() as cur:

            # Antalya'nın iller tablosunda
            # bulunduğunu kontrol ediyoruz.
            cur.execute(
                """
                SELECT id, name
                FROM iller
                WHERE id = %s
                """,
                (ANTALYA_ID,)
            )

            il = cur.fetchone()

            if il is None:
                raise ValueError(
                    "Antalya iller tablosunda bulunamadı. "
                    "Önce il_scraper.py dosyasını çalıştır."
                )

            print("Bağlı il:", il[1])

            print("\n--- İLÇELER KAYDEDİLİYOR ---")

            for feature in features:

                properties = (
                    feature.get("properties") or {}
                )

                geometry = feature.get("geometry")

                raw_id = properties.get("id")
                raw_name = properties.get("text")

                if not raw_id or not raw_name:
                    raise ValueError(
                        "İlçe kaydında id veya text eksik: "
                        f"{properties}"
                    )

                # UUID dönüşümü
                ilce_id = uuid.UUID(
                    str(raw_id).strip("{}")
                )

                ilce_name = str(raw_name).strip()

                # GeoJSON -> JSON metni
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
                        ilce_id,
                        ilce_name,
                        ANTALYA_ID,
                        geometry_json,
                        geometry_json,
                        Jsonb(properties),
                        Jsonb(geometry)
                    )
                )

                saved_count += 1

                print(
                    f"[{saved_count}/{len(features)}] "
                    f"Kaydedildi: {ilce_name}"
                )

    # with bloğundan sorunsuz çıkılırsa
    # transaction commit edilir.
    return saved_count


# ==========================================
# 5. VERİTABANI DOĞRULAMA
# ==========================================

def verify_ilceler():

    with psycopg.connect(**DB_CONFIG) as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    COUNT(*) AS toplam,
                    COUNT(geometry) AS geometrili,
                    COUNT(*) FILTER (
                        WHERE geometry IS NOT NULL
                          AND ST_IsValid(geometry)
                    ) AS gecerli_geometri
                FROM ilceler
                WHERE il_id = %s
                """,
                (ANTALYA_ID,)
            )

            toplam, geometrili, gecerli = cur.fetchone()

            print("\n--- VERİTABANI KONTROLÜ ---")
            print("Toplam ilçe:", toplam)
            print("Geometrisi bulunan:", geometrili)
            print("Geometrisi geçerli:", gecerli)


# ==========================================
# 6. PROGRAMIN BAŞLANGICI
# ==========================================

def main():

    try:
        features = fetch_ilceler()

        print(
            f"\nAPI'den {len(features)} ilçe alındı."
        )

        saved_count = save_ilceler(features)

        verify_ilceler()

        print("\n" + "=" * 55)
        print("İŞLEM TAMAMLANDI")
        print(f"İşlenen ilçe sayısı: {saved_count}")
        print("=" * 55)

    except requests.exceptions.RequestException as exc:
        print("\nAPI bağlantı hatası:")
        print(exc)
        raise

    except psycopg.Error as exc:
        print("\nPostgreSQL hatası:")
        print(exc)
        raise

    except Exception as exc:
        print("\nİşlem başarısız:")
        print(exc)
        raise


if __name__ == "__main__":
    main()
