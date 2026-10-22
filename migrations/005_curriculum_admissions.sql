/*
    Reusable curriculum structure and admissions leads.
    Preconditions: apply migrations 002_academic_management.sql and
    003_training_programs.sql first, then run this script in the app database.
    Safe to run repeatedly. Roles 1-8 must already exist; app startup seeds them.
*/
SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF COL_LENGTH(N'dbo.MonHoc', N'SoBuoi') IS NULL
    ALTER TABLE dbo.MonHoc ADD SoBuoi INT NOT NULL
        CONSTRAINT DF_MonHoc_SoBuoi DEFAULT 1;

IF COL_LENGTH(N'dbo.MonHoc', N'TrongSo') IS NULL
    ALTER TABLE dbo.MonHoc ADD TrongSo DECIMAL(5,2) NOT NULL
        CONSTRAINT DF_MonHoc_TrongSo DEFAULT 1;

IF COL_LENGTH(N'dbo.MonHoc', N'MoTaChuanDauRa') IS NULL
    ALTER TABLE dbo.MonHoc ADD MoTaChuanDauRa NVARCHAR(1000) NULL;

IF NOT EXISTS
(
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.MonHoc')
      AND name = N'CK_MonHoc_SoBuoi'
)
    EXEC sys.sp_executesql
        N'ALTER TABLE dbo.MonHoc
          ADD CONSTRAINT CK_MonHoc_SoBuoi CHECK (SoBuoi > 0);';

IF NOT EXISTS
(
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.MonHoc')
      AND name = N'CK_MonHoc_TrongSo'
)
    EXEC sys.sp_executesql
        N'ALTER TABLE dbo.MonHoc
          ADD CONSTRAINT CK_MonHoc_TrongSo
          CHECK (TrongSo >= 0 AND TrongSo <= 1);';

IF OBJECT_ID(N'dbo.ChuongTrinh_MonHoc', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ChuongTrinh_MonHoc
    (
        ChuongTrinhMonHocId INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_ChuongTrinh_MonHoc PRIMARY KEY,
        ChuongTrinhId INT NOT NULL,
        MonHocId INT NOT NULL,
        ThuTu INT NOT NULL,
        CONSTRAINT UQ_ChuongTrinh_MonHoc
            UNIQUE (ChuongTrinhId, MonHocId),
        CONSTRAINT UQ_ChuongTrinh_MonHoc_ThuTu
            UNIQUE (ChuongTrinhId, ThuTu),
        CONSTRAINT CK_ChuongTrinh_MonHoc_ThuTu CHECK (ThuTu > 0),
        CONSTRAINT FK_ChuongTrinh_MonHoc_ChuongTrinh
            FOREIGN KEY (ChuongTrinhId)
            REFERENCES dbo.ChuongTrinhDaoTao(ChuongTrinhId),
        CONSTRAINT FK_ChuongTrinh_MonHoc_MonHoc
            FOREIGN KEY (MonHocId) REFERENCES dbo.MonHoc(MonHocId)
    );
END;

IF OBJECT_ID(N'dbo.ChuongTrinh_MonHoc_TienQuyet', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.ChuongTrinh_MonHoc_TienQuyet
    (
        ChuongTrinhMonHocId INT NOT NULL,
        MonTienQuyetId INT NOT NULL,
        CONSTRAINT PK_ChuongTrinh_MonHoc_TienQuyet
            PRIMARY KEY (ChuongTrinhMonHocId, MonTienQuyetId),
        CONSTRAINT CK_ChuongTrinh_MonHoc_TienQuyet_KhacNhau
            CHECK (ChuongTrinhMonHocId <> MonTienQuyetId),
        CONSTRAINT FK_ChuongTrinh_MonHoc_TienQuyet_Child
            FOREIGN KEY (ChuongTrinhMonHocId)
            REFERENCES dbo.ChuongTrinh_MonHoc(ChuongTrinhMonHocId),
        CONSTRAINT FK_ChuongTrinh_MonHoc_TienQuyet_Parent
            FOREIGN KEY (MonTienQuyetId)
            REFERENCES dbo.ChuongTrinh_MonHoc(ChuongTrinhMonHocId)
    );
END;

IF OBJECT_ID(N'dbo.BuoiHoc', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.BuoiHoc
    (
        BuoiHocId INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_BuoiHoc PRIMARY KEY,
        ChuongTrinhMonHocId INT NOT NULL,
        SoThuTu INT NOT NULL,
        ChuDe NVARCHAR(200) NOT NULL,
        MucTieu NVARCHAR(1000) NULL,
        CONSTRAINT UQ_BuoiHoc_ChuongTrinhMonHoc_ThuTu
            UNIQUE (ChuongTrinhMonHocId, SoThuTu),
        CONSTRAINT CK_BuoiHoc_SoThuTu CHECK (SoThuTu > 0),
        CONSTRAINT FK_BuoiHoc_ChuongTrinhMonHoc
            FOREIGN KEY (ChuongTrinhMonHocId)
            REFERENCES dbo.ChuongTrinh_MonHoc(ChuongTrinhMonHocId)
    );
END;

IF OBJECT_ID(N'dbo.TuyenSinh_Lead', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.TuyenSinh_Lead
    (
        LeadId INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_TuyenSinh_Lead PRIMARY KEY,
        HoTen NVARCHAR(100) NOT NULL,
        SoDienThoai VARCHAR(30) NOT NULL,
        Email VARCHAR(255) NULL,
        Nguon NVARCHAR(100) NOT NULL,
        GhiChu NVARCHAR(1000) NULL,
        ChuongTrinhId INT NULL,
        TrangThai NVARCHAR(30) NOT NULL
            CONSTRAINT DF_TuyenSinh_Lead_TrangThai DEFAULT N'Mới',
        NgayTao DATETIME2 NOT NULL
            CONSTRAINT DF_TuyenSinh_Lead_NgayTao DEFAULT SYSUTCDATETIME(),
        NgayCapNhat DATETIME2 NOT NULL
            CONSTRAINT DF_TuyenSinh_Lead_NgayCapNhat DEFAULT SYSUTCDATETIME(),
        NguoiTaoId INT NULL,
        CONSTRAINT CK_TuyenSinh_Lead_TrangThai CHECK
            (TrangThai IN (N'Mới', N'Đang liên hệ', N'Tiềm năng',
                           N'Đã chuyển đổi', N'Không tiềm năng')),
        CONSTRAINT FK_TuyenSinh_Lead_ChuongTrinh
            FOREIGN KEY (ChuongTrinhId)
            REFERENCES dbo.ChuongTrinhDaoTao(ChuongTrinhId),
        CONSTRAINT FK_TuyenSinh_Lead_NguoiTao
            FOREIGN KEY (NguoiTaoId) REFERENCES dbo.NguoiDung(NguoiDungId)
    );
END;

IF EXISTS
(
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.TuyenSinh_Lead')
      AND name = N'ChuongTrinhId'
      AND is_nullable = 0
)
    ALTER TABLE dbo.TuyenSinh_Lead ALTER COLUMN ChuongTrinhId INT NULL;

IF COL_LENGTH(N'dbo.TuyenSinh_Lead', N'GhiChu') IS NULL
    ALTER TABLE dbo.TuyenSinh_Lead ADD GhiChu NVARCHAR(1000) NULL;

IF OBJECT_ID(N'dbo.TuyenSinh_Lead_PhanCong', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.TuyenSinh_Lead_PhanCong
    (
        PhanCongId INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_TuyenSinh_Lead_PhanCong PRIMARY KEY,
        LeadId INT NOT NULL,
        NguoiDungId INT NOT NULL,
        NguoiPhanCongId INT NOT NULL,
        NgayPhanCong DATETIME2 NOT NULL
            CONSTRAINT DF_TuyenSinh_Lead_PhanCong_NgayTao
            DEFAULT SYSUTCDATETIME(),
        NgayBoPhanCong DATETIME2 NULL,
        DangPhanCong BIT NOT NULL
            CONSTRAINT DF_TuyenSinh_Lead_PhanCong_DangPhanCong DEFAULT 1,
        CONSTRAINT FK_TuyenSinh_Lead_PhanCong_Lead
            FOREIGN KEY (LeadId) REFERENCES dbo.TuyenSinh_Lead(LeadId),
        CONSTRAINT FK_TuyenSinh_Lead_PhanCong_NguoiDung
            FOREIGN KEY (NguoiDungId) REFERENCES dbo.NguoiDung(NguoiDungId),
        CONSTRAINT FK_TuyenSinh_Lead_PhanCong_NguoiPhanCong
            FOREIGN KEY (NguoiPhanCongId) REFERENCES dbo.NguoiDung(NguoiDungId)
    );
END;

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.TuyenSinh_Lead')
      AND name = N'IX_TuyenSinh_Lead_TrangThai_NgayTao'
)
    CREATE INDEX IX_TuyenSinh_Lead_TrangThai_NgayTao
        ON dbo.TuyenSinh_Lead(TrangThai, NgayTao DESC);

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.TuyenSinh_Lead')
      AND name = N'IX_TuyenSinh_Lead_SoDienThoai'
)
    CREATE INDEX IX_TuyenSinh_Lead_SoDienThoai
        ON dbo.TuyenSinh_Lead(SoDienThoai);

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.TuyenSinh_Lead_PhanCong')
      AND name = N'IX_TuyenSinh_Lead_PhanCong_NguoiDung'
)
    CREATE INDEX IX_TuyenSinh_Lead_PhanCong_NguoiDung
        ON dbo.TuyenSinh_Lead_PhanCong(NguoiDungId, DangPhanCong, LeadId);

INSERT INTO dbo.Quyen (MaQuyen, TenQuyen, MoTa)
SELECT p.MaQuyen, p.TenQuyen, p.MoTa
FROM (VALUES
    ('CURRICULUM_VIEW', N'Xem danh mục đào tạo', N'Xem môn học và cấu trúc chương trình.'),
    ('CURRICULUM_CREATE', N'Tạo danh mục đào tạo', N'Tạo môn học trong danh mục đào tạo.'),
    ('CURRICULUM_UPDATE', N'Sửa danh mục đào tạo', N'Sửa môn học và cấu trúc chương trình.'),
    ('CURRICULUM_DELETE', N'Lưu trữ danh mục đào tạo', N'Lưu trữ môn học trong danh mục đào tạo.'),
    ('LEAD_VIEW', N'Xem khách hàng tiềm năng', N'Xem hồ sơ tuyển sinh được phép truy cập.'),
    ('LEAD_CREATE', N'Tạo khách hàng tiềm năng', N'Tạo hồ sơ khách hàng tiềm năng.'),
    ('LEAD_UPDATE', N'Sửa khách hàng tiềm năng', N'Cập nhật hồ sơ khách hàng tiềm năng.'),
    ('LEAD_DELETE', N'Xóa khách hàng tiềm năng', N'Xóa hồ sơ khách hàng tiềm năng.'),
    ('LEAD_ASSIGN', N'Phân công tư vấn', N'Phân công khách hàng tiềm năng cho tư vấn viên.')
) AS p(MaQuyen, TenQuyen, MoTa)
WHERE NOT EXISTS
(
    SELECT 1 FROM dbo.Quyen q WHERE q.MaQuyen = p.MaQuyen
);

INSERT INTO dbo.VaiTro_Quyen (VaiTroId, QuyenId)
SELECT role_grants.VaiTroId, q.QuyenId
FROM (VALUES
    (5, 'LEAD_VIEW'),
    (5, 'LEAD_CREATE'),
    (5, 'LEAD_UPDATE'),
    (7, 'CURRICULUM_VIEW'),
    (7, 'CURRICULUM_CREATE'),
    (7, 'CURRICULUM_UPDATE'),
    (7, 'CURRICULUM_DELETE'),
    (7, 'LEAD_VIEW'),
    (7, 'LEAD_CREATE'),
    (7, 'LEAD_UPDATE'),
    (7, 'LEAD_DELETE'),
    (7, 'LEAD_ASSIGN'),
    (8, 'CURRICULUM_VIEW'),
    (8, 'CURRICULUM_CREATE'),
    (8, 'CURRICULUM_UPDATE'),
    (8, 'CURRICULUM_DELETE'),
    (8, 'LEAD_VIEW'),
    (8, 'LEAD_CREATE'),
    (8, 'LEAD_UPDATE'),
    (8, 'LEAD_DELETE'),
    (8, 'LEAD_ASSIGN')
) AS role_grants(VaiTroId, MaQuyen)
INNER JOIN dbo.Quyen q ON q.MaQuyen = role_grants.MaQuyen
WHERE NOT EXISTS
(
    SELECT 1
    FROM dbo.VaiTro_Quyen existing
    WHERE existing.VaiTroId = role_grants.VaiTroId
      AND existing.QuyenId = q.QuyenId
);

COMMIT TRANSACTION;
