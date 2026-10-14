/*
    Sprint 3: lead workflow and touchpoints, student/class lifecycle,
    enrollment audit, room capacity, and subject-level teaching assignments.
    Apply after migrations 002-007. Safe to rerun.
*/
SET ANSI_NULLS ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET QUOTED_IDENTIFIER ON;
SET NUMERIC_ROUNDABORT OFF;
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF COL_LENGTH(N'dbo.TuyenSinh_Lead', N'LyDoTuChoi') IS NULL
        ALTER TABLE dbo.TuyenSinh_Lead ADD LyDoTuChoi NVARCHAR(500) NULL;

    IF EXISTS
    (
        SELECT 1 FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.TuyenSinh_Lead')
          AND name = N'CK_TuyenSinh_Lead_TrangThai'
    )
        ALTER TABLE dbo.TuyenSinh_Lead
            DROP CONSTRAINT CK_TuyenSinh_Lead_TrangThai;

    ALTER TABLE dbo.TuyenSinh_Lead
        ADD CONSTRAINT CK_TuyenSinh_Lead_TrangThai
        CHECK (TrangThai IN
        (
            N'Mới', N'Đã liên hệ', N'Đang tư vấn', N'Hẹn học thử',
            N'Chốt', N'Từ chối',
            N'Đang liên hệ', N'Tiềm năng', N'Đã chuyển đổi',
            N'Đã nhập học', N'Không tiềm năng'
        ));

    IF OBJECT_ID(N'dbo.TuyenSinh_Lead_LichSuTrangThai', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.TuyenSinh_Lead_LichSuTrangThai
        (
            LichSuId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_TuyenSinh_Lead_LichSuTrangThai PRIMARY KEY,
            LeadId INT NOT NULL,
            TrangThaiCu NVARCHAR(30) NULL,
            TrangThaiMoi NVARCHAR(30) NOT NULL,
            LyDo NVARCHAR(500) NULL,
            NguoiThucHienId INT NOT NULL,
            ThoiDiem DATETIME2 NOT NULL
                CONSTRAINT DF_TuyenSinh_Lead_LichSu_ThoiDiem DEFAULT SYSUTCDATETIME(),
            CONSTRAINT FK_TuyenSinh_Lead_LichSu_Lead
                FOREIGN KEY (LeadId) REFERENCES dbo.TuyenSinh_Lead(LeadId),
            CONSTRAINT FK_TuyenSinh_Lead_LichSu_NguoiDung
                FOREIGN KEY (NguoiThucHienId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );
    END;

    IF OBJECT_ID(N'dbo.TuyenSinh_Lead_TuongTac', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.TuyenSinh_Lead_TuongTac
        (
            TuongTacId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_TuyenSinh_Lead_TuongTac PRIMARY KEY,
            LeadId INT NOT NULL,
            Loai NVARCHAR(20) NOT NULL,
            NoiDung NVARCHAR(2000) NOT NULL,
            ThoiDiem DATETIME2 NOT NULL,
            HenGoiLaiLuc DATETIME2 NULL,
            NguoiThucHienId INT NOT NULL,
            NgayTao DATETIME2 NOT NULL
                CONSTRAINT DF_TuyenSinh_Lead_TuongTac_NgayTao DEFAULT SYSUTCDATETIME(),
            CONSTRAINT CK_TuyenSinh_Lead_TuongTac_Loai
                CHECK (Loai IN (N'Gọi', N'Nhắn tin', N'Gặp')),
            CONSTRAINT FK_TuyenSinh_Lead_TuongTac_Lead
                FOREIGN KEY (LeadId) REFERENCES dbo.TuyenSinh_Lead(LeadId),
            CONSTRAINT FK_TuyenSinh_Lead_TuongTac_NguoiDung
                FOREIGN KEY (NguoiThucHienId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );
    END;

    IF NOT EXISTS
    (
        SELECT 1 FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.TuyenSinh_Lead_TuongTac')
          AND name = N'IX_TuyenSinh_Lead_TuongTac_HenGoiLai'
    )
        CREATE INDEX IX_TuyenSinh_Lead_TuongTac_HenGoiLai
            ON dbo.TuyenSinh_Lead_TuongTac(HenGoiLaiLuc, LeadId)
            WHERE HenGoiLaiLuc IS NOT NULL;

    IF OBJECT_ID(N'dbo.PhongHoc', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.PhongHoc
        (
            PhongHocId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_PhongHoc PRIMARY KEY,
            MaPhong NVARCHAR(30) NOT NULL
                CONSTRAINT UQ_PhongHoc_MaPhong UNIQUE,
            TenPhong NVARCHAR(100) NOT NULL,
            SucChua INT NOT NULL,
            TrangThai NVARCHAR(20) NOT NULL
                CONSTRAINT DF_PhongHoc_TrangThai DEFAULT N'Đang hoạt động',
            CONSTRAINT CK_PhongHoc_SucChua CHECK (SucChua > 0),
            CONSTRAINT CK_PhongHoc_TrangThai
                CHECK (TrangThai IN (N'Đang hoạt động', N'Ngừng hoạt động'))
        );
    END;

    IF COL_LENGTH(N'dbo.LopHoc', N'NgayKhaiGiang') IS NULL
        ALTER TABLE dbo.LopHoc ADD NgayKhaiGiang DATE NULL;

    IF COL_LENGTH(N'dbo.LopHoc', N'SiSoToiDa') IS NULL
        ALTER TABLE dbo.LopHoc ADD SiSoToiDa INT NOT NULL
            CONSTRAINT DF_LopHoc_SiSoToiDa DEFAULT 30;
    IF COL_LENGTH(N'dbo.LopHoc', N'HinhThuc') IS NULL
        ALTER TABLE dbo.LopHoc ADD HinhThuc NVARCHAR(20) NOT NULL
            CONSTRAINT DF_LopHoc_HinhThuc DEFAULT N'Trực tiếp';
    IF COL_LENGTH(N'dbo.LopHoc', N'PhongHocId') IS NULL
        ALTER TABLE dbo.LopHoc ADD PhongHocId INT NULL;
    IF COL_LENGTH(N'dbo.LopHoc', N'LinkTrucTuyen') IS NULL
        ALTER TABLE dbo.LopHoc ADD LinkTrucTuyen NVARCHAR(500) NULL;
    IF COL_LENGTH(N'dbo.LopHoc', N'TienDo') IS NULL
        ALTER TABLE dbo.LopHoc ADD TienDo DECIMAL(5,2) NOT NULL
            CONSTRAINT DF_LopHoc_TienDo DEFAULT 0;

    EXEC sys.sp_executesql N'
        UPDATE dbo.LopHoc SET NgayKhaiGiang = CAST(NgayTao AS DATE)
        WHERE NgayKhaiGiang IS NULL;
        ALTER TABLE dbo.LopHoc ALTER COLUMN NgayKhaiGiang DATE NOT NULL;

        IF NOT EXISTS
        (
            SELECT 1 FROM sys.foreign_keys
            WHERE parent_object_id = OBJECT_ID(N''dbo.LopHoc'')
              AND name = N''FK_LopHoc_PhongHoc''
        )
            ALTER TABLE dbo.LopHoc ADD CONSTRAINT FK_LopHoc_PhongHoc
                FOREIGN KEY (PhongHocId) REFERENCES dbo.PhongHoc(PhongHocId);

        IF NOT EXISTS
        (
            SELECT 1 FROM sys.check_constraints
            WHERE parent_object_id = OBJECT_ID(N''dbo.LopHoc'')
              AND name = N''CK_LopHoc_SiSoToiDa''
        )
            ALTER TABLE dbo.LopHoc ADD CONSTRAINT CK_LopHoc_SiSoToiDa
                CHECK (SiSoToiDa > 0);
        IF NOT EXISTS
        (
            SELECT 1 FROM sys.check_constraints
            WHERE parent_object_id = OBJECT_ID(N''dbo.LopHoc'')
              AND name = N''CK_LopHoc_HinhThuc''
        )
            ALTER TABLE dbo.LopHoc ADD CONSTRAINT CK_LopHoc_HinhThuc
                CHECK (HinhThuc IN (N''Trực tiếp'', N''Trực tuyến'', N''Kết hợp''));
        IF NOT EXISTS
        (
            SELECT 1 FROM sys.check_constraints
            WHERE parent_object_id = OBJECT_ID(N''dbo.LopHoc'')
              AND name = N''CK_LopHoc_TienDo''
        )
            ALTER TABLE dbo.LopHoc ADD CONSTRAINT CK_LopHoc_TienDo
                CHECK (TienDo BETWEEN 0 AND 100);
    ';

    UPDATE dbo.LopHoc SET TrangThai = N'Chuẩn bị'
    WHERE TrangThai = N'Đang hoạt động';

    IF COL_LENGTH(N'dbo.LopHoc_HocVien', N'NguoiGhiDanhId') IS NULL
        ALTER TABLE dbo.LopHoc_HocVien ADD NguoiGhiDanhId INT NULL;
    EXEC sys.sp_executesql N'
        IF NOT EXISTS
        (
            SELECT 1 FROM sys.foreign_keys
            WHERE parent_object_id = OBJECT_ID(N''dbo.LopHoc_HocVien'')
              AND name = N''FK_LopHoc_HocVien_NguoiGhiDanh''
        )
            ALTER TABLE dbo.LopHoc_HocVien
                ADD CONSTRAINT FK_LopHoc_HocVien_NguoiGhiDanh
                FOREIGN KEY (NguoiGhiDanhId)
                REFERENCES dbo.NguoiDung(NguoiDungId);
    ';

    IF OBJECT_ID(N'dbo.LopHoc_MonHoc_GiangVien', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LopHoc_MonHoc_GiangVien
        (
            LopHocId INT NOT NULL,
            MonHocId INT NOT NULL,
            GiangVienId INT NOT NULL,
            VaiTro NVARCHAR(20) NOT NULL,
            CONSTRAINT PK_LopHoc_MonHoc_GiangVien
                PRIMARY KEY (LopHocId, MonHocId, GiangVienId),
            CONSTRAINT CK_LopHoc_MonHoc_GiangVien_VaiTro
                CHECK (VaiTro IN (N'Chính', N'Trợ giảng')),
            CONSTRAINT FK_LopHoc_MonHoc_GiangVien_MonHoc
                FOREIGN KEY (LopHocId, MonHocId)
                REFERENCES dbo.LopHoc_MonHoc(LopHocId, MonHocId),
            CONSTRAINT FK_LopHoc_MonHoc_GiangVien_NguoiDung
                FOREIGN KEY (GiangVienId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );
    END;

    IF NOT EXISTS
    (
        SELECT 1 FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.LopHoc_MonHoc_GiangVien')
          AND name = N'UX_LopHoc_MonHoc_GiangVien_Chinh'
    )
        CREATE UNIQUE INDEX UX_LopHoc_MonHoc_GiangVien_Chinh
            ON dbo.LopHoc_MonHoc_GiangVien(LopHocId, MonHocId)
            WHERE VaiTro = N'Chính';

    INSERT INTO dbo.LopHoc_MonHoc_GiangVien
        (LopHocId, MonHocId, GiangVienId, VaiTro)
    SELECT lm.LopHocId, lm.MonHocId, l.GiangVienId, N'Chính'
    FROM dbo.LopHoc_MonHoc AS lm
    INNER JOIN dbo.LopHoc AS l ON l.LopHocId = lm.LopHocId
    WHERE l.GiangVienId IS NOT NULL
      AND NOT EXISTS
      (
          SELECT 1 FROM dbo.LopHoc_MonHoc_GiangVien AS a
          WHERE a.LopHocId = lm.LopHocId
            AND a.MonHocId = lm.MonHocId
            AND a.VaiTro = N'Chính'
      );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
