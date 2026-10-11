/*
    Academic management schema.
    Run once against the configured SQL Server database after the app has
    initialized its eight roles and permission catalog.
*/

SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.MonHoc', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.MonHoc
    (
        MonHocId INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_MonHoc PRIMARY KEY,
        MaMonHoc NVARCHAR(30) NOT NULL
            CONSTRAINT UQ_MonHoc_MaMonHoc UNIQUE,
        TenMonHoc NVARCHAR(150) NOT NULL,
        SoTinChi INT NULL
            CONSTRAINT CK_MonHoc_SoTinChi
            CHECK (SoTinChi IS NULL OR SoTinChi BETWEEN 1 AND 30),
        TrangThai NVARCHAR(30) NOT NULL
            CONSTRAINT DF_MonHoc_TrangThai DEFAULT N'Đang hoạt động'
    );
END;

IF OBJECT_ID(N'dbo.LopHoc', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.LopHoc
    (
        LopHocId INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_LopHoc PRIMARY KEY,
        MaLop NVARCHAR(30) NOT NULL
            CONSTRAINT UQ_LopHoc_MaLop UNIQUE,
        TenLop NVARCHAR(100) NOT NULL,
        NamHoc NVARCHAR(9) NOT NULL,
        GiangVienId INT NULL,
        TrangThai NVARCHAR(30) NOT NULL
            CONSTRAINT DF_LopHoc_TrangThai DEFAULT N'Đang hoạt động',
        NgayTao DATETIME2 NOT NULL
            CONSTRAINT DF_LopHoc_NgayTao DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_LopHoc_GiangVien
            FOREIGN KEY (GiangVienId)
            REFERENCES dbo.NguoiDung(NguoiDungId)
    );
END;

IF OBJECT_ID(N'dbo.LopHoc_HocVien', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.LopHoc_HocVien
    (
        LopHocId INT NOT NULL,
        HocVienId INT NOT NULL,
        NgayThamGia DATETIME2 NOT NULL
            CONSTRAINT DF_LopHoc_HocVien_NgayThamGia DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_LopHoc_HocVien PRIMARY KEY (LopHocId, HocVienId),
        CONSTRAINT FK_LopHoc_HocVien_LopHoc
            FOREIGN KEY (LopHocId) REFERENCES dbo.LopHoc(LopHocId),
        CONSTRAINT FK_LopHoc_HocVien_NguoiDung
            FOREIGN KEY (HocVienId) REFERENCES dbo.NguoiDung(NguoiDungId)
    );
END;

IF OBJECT_ID(N'dbo.LopHoc_MonHoc', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.LopHoc_MonHoc
    (
        LopHocId INT NOT NULL,
        MonHocId INT NOT NULL,
        CONSTRAINT PK_LopHoc_MonHoc PRIMARY KEY (LopHocId, MonHocId),
        CONSTRAINT FK_LopHoc_MonHoc_LopHoc
            FOREIGN KEY (LopHocId) REFERENCES dbo.LopHoc(LopHocId),
        CONSTRAINT FK_LopHoc_MonHoc_MonHoc
            FOREIGN KEY (MonHocId) REFERENCES dbo.MonHoc(MonHocId)
    );
END;

IF COL_LENGTH(N'dbo.LopHoc_MonHoc', N'ThuTu') IS NULL
BEGIN
    ALTER TABLE dbo.LopHoc_MonHoc
    ADD ThuTu INT NOT NULL
        CONSTRAINT DF_LopHoc_MonHoc_ThuTu DEFAULT 1;
END;


IF OBJECT_ID(N'dbo.Diem', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Diem
    (
        DiemId INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_Diem PRIMARY KEY,
        LopHocId INT NOT NULL,
        HocVienId INT NOT NULL,
        MonHocId INT NOT NULL,
        HocKy INT NOT NULL
            CONSTRAINT CK_Diem_HocKy CHECK (HocKy BETWEEN 1 AND 3),
        NamHoc NVARCHAR(9) NOT NULL,
        DiemQuaTrinh DECIMAL(4,2) NULL
            CONSTRAINT CK_Diem_DiemQuaTrinh
            CHECK (DiemQuaTrinh IS NULL OR DiemQuaTrinh BETWEEN 0 AND 10),
        DiemGiuaKy DECIMAL(4,2) NULL
            CONSTRAINT CK_Diem_DiemGiuaKy
            CHECK (DiemGiuaKy IS NULL OR DiemGiuaKy BETWEEN 0 AND 10),
        DiemCuoiKy DECIMAL(4,2) NULL
            CONSTRAINT CK_Diem_DiemCuoiKy
            CHECK (DiemCuoiKy IS NULL OR DiemCuoiKy BETWEEN 0 AND 10),
        NgayTao DATETIME2 NOT NULL
            CONSTRAINT DF_Diem_NgayTao DEFAULT SYSUTCDATETIME(),
        NgayCapNhat DATETIME2 NOT NULL
            CONSTRAINT DF_Diem_NgayCapNhat DEFAULT SYSUTCDATETIME(),
        CONSTRAINT UQ_Diem_HocVien_Lop_Mon_HocKy_NamHoc
            UNIQUE (LopHocId, HocVienId, MonHocId, HocKy, NamHoc),
        CONSTRAINT FK_Diem_LopHoc_HocVien
            FOREIGN KEY (LopHocId, HocVienId)
            REFERENCES dbo.LopHoc_HocVien(LopHocId, HocVienId),
        CONSTRAINT FK_Diem_LopHoc_MonHoc
            FOREIGN KEY (LopHocId, MonHocId)
            REFERENCES dbo.LopHoc_MonHoc(LopHocId, MonHocId)
    );

END;

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.LopHoc')
      AND name = N'IX_LopHoc_GiangVien'
)
    CREATE INDEX IX_LopHoc_GiangVien ON dbo.LopHoc(GiangVienId, TrangThai);

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.LopHoc_HocVien')
      AND name = N'IX_LopHoc_HocVien_HocVien'
)
    CREATE INDEX IX_LopHoc_HocVien_HocVien
        ON dbo.LopHoc_HocVien(HocVienId, LopHocId);

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.Diem')
      AND name = N'IX_Diem_HocVien'
)
    CREATE INDEX IX_Diem_HocVien ON dbo.Diem(HocVienId, NamHoc, HocKy);

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.Diem')
      AND name = N'IX_Diem_LopHoc'
)
    CREATE INDEX IX_Diem_LopHoc ON dbo.Diem(LopHocId, MonHocId);

/*
    Existing deployments already have the permission codes from the RBAC
    bootstrap. Add agreed grants without replacing unrelated grants, and
    revoke the old default grade-view grant from teaching assistants.
*/
INSERT INTO dbo.VaiTro_Quyen (VaiTroId, QuyenId)
SELECT defaults.VaiTroId, q.QuyenId
FROM (VALUES
    (3, 'CLASS_VIEW'),
    (7, 'CLASS_CREATE'),
    (7, 'CLASS_UPDATE'),
    (7, 'CLASS_DELETE')
) AS defaults(VaiTroId, MaQuyen)
INNER JOIN dbo.Quyen AS q ON q.MaQuyen = defaults.MaQuyen
WHERE NOT EXISTS
(
    SELECT 1
    FROM dbo.VaiTro_Quyen AS existing
    WHERE existing.VaiTroId = defaults.VaiTroId
      AND existing.QuyenId = q.QuyenId
);

DELETE FROM dbo.VaiTro_Quyen
WHERE VaiTroId = 4
  AND QuyenId IN
  (
      SELECT QuyenId FROM dbo.Quyen WHERE MaQuyen = 'GRADE_VIEW'
  );

COMMIT TRANSACTION;
