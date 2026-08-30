import csv
from app.database.database import SessionLocal
from sqlalchemy import text

FILE_PATH = r"C:\ubuntu\uszips.csv"

def load_zipcodes():
    db = SessionLocal()

    print("Eliminando registros previos de zipcodes...")
    db.execute(text("DELETE FROM zipcodes"))
    db.commit()

    print("Cargando ZIP Codes...")

    with open(FILE_PATH, "r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        count = 0
        for row in reader:
            zip_code = row["zip"].strip()
            city = row["city"].strip()
            state = row["state_id"].strip()

            db.execute(
                text("""
                    INSERT INTO zipcodes (zip_code, city, state)
                    VALUES (:zip_code, :city, :state)
                """),
                {"zip_code": zip_code, "city": city, "state": state}
            )

            count += 1
            if count % 500 == 0:
                print(f"{count} ZIP Codes insertados...")

        db.commit()

    print(f"Proceso completado. Total ZIP Codes insertados: {count}")

if __name__ == "__main__":
    load_zipcodes()
