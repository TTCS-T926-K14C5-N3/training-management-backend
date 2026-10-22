from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    # 1. Add LoaiPhong column if not exists
    res = conn.execute(text("SELECT COL_LENGTH(N'dbo.PhongHoc', N'LoaiPhong')")).scalar()
    if res is None:
        conn.execute(text("ALTER TABLE dbo.PhongHoc ADD LoaiPhong NVARCHAR(20) NOT NULL CONSTRAINT DF_PhongHoc_LoaiPhong DEFAULT N'Trực tiếp' WITH VALUES"))
        conn.commit()
        print("Added LoaiPhong column!")
    else:
        print("LoaiPhong already exists.")

    # 2. Add constraint
    has_ck = conn.execute(text("SELECT 1 FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID(N'dbo.PhongHoc') AND name = N'CK_PhongHoc_LoaiPhong'")).scalar()
    if not has_ck:
        conn.execute(text("ALTER TABLE dbo.PhongHoc ADD CONSTRAINT CK_PhongHoc_LoaiPhong CHECK (LoaiPhong IN (N'Trực tiếp', N'Trực tuyến'))"))
        conn.commit()
        print("Added CK_PhongHoc_LoaiPhong constraint!")
