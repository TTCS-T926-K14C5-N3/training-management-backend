SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF COL_LENGTH(N'dbo.LopHoc_HocVien', N'TrangThaiGhiDanh') IS NULL
        ALTER TABLE dbo.LopHoc_HocVien ADD TrangThaiGhiDanh NVARCHAR(20) NOT NULL
            CONSTRAINT DF_LopHoc_HocVien_TrangThaiGhiDanh DEFAULT N'Đang học' WITH VALUES;

    IF COL_LENGTH(N'dbo.LopHoc_HocVien', N'NgayKetThuc') IS NULL
        ALTER TABLE dbo.LopHoc_HocVien ADD NgayKetThuc DATETIME2 NULL;

    IF NOT EXISTS
    (
        SELECT 1 FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.LopHoc_HocVien')
          AND name = N'CK_LopHoc_HocVien_TrangThaiGhiDanh'
    )
    BEGIN
        EXEC sys.sp_executesql N'
            ALTER TABLE dbo.LopHoc_HocVien
            ADD CONSTRAINT CK_LopHoc_HocVien_TrangThaiGhiDanh
            CHECK (TrangThaiGhiDanh IN
                (N''Đang học'', N''Bảo lưu'', N''Chuyển lớp'', N''Thôi học''));
        ';
    END;

    IF OBJECT_ID(N'dbo.LopHoc_HocVien_ThaoTac', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LopHoc_HocVien_ThaoTac
        (
            ThaoTacId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_LopHoc_HocVien_ThaoTac PRIMARY KEY,
            LopHocId INT NOT NULL,
            HocVienId INT NOT NULL,
            LoaiThaoTac NVARCHAR(20) NOT NULL,
            NgayHieuLuc DATETIME2 NOT NULL,
            LopHocDichId INT NULL,
            LyDo NVARCHAR(1000) NOT NULL,
            NguoiThucHienId INT NOT NULL,
            NgayTao DATETIME2 NOT NULL,
            CONSTRAINT CK_LopHoc_HocVien_ThaoTac_Loai
                CHECK (LoaiThaoTac IN (N'BaoLuu', N'ChuyenLop', N'ThoiHoc')),
            CONSTRAINT CK_LopHoc_HocVien_ThaoTac_Dich
                CHECK ((LoaiThaoTac = N'ChuyenLop' AND LopHocDichId IS NOT NULL)
                    OR (LoaiThaoTac <> N'ChuyenLop' AND LopHocDichId IS NULL)),
            CONSTRAINT FK_LopHoc_HocVien_ThaoTac_Lop
                FOREIGN KEY (LopHocId) REFERENCES dbo.LopHoc(LopHocId),
            CONSTRAINT FK_LopHoc_HocVien_ThaoTac_HocVien
                FOREIGN KEY (HocVienId) REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_LopHoc_HocVien_ThaoTac_LopDich
                FOREIGN KEY (LopHocDichId) REFERENCES dbo.LopHoc(LopHocId),
            CONSTRAINT FK_LopHoc_HocVien_ThaoTac_NguoiThucHien
                FOREIGN KEY (NguoiThucHienId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );
        CREATE INDEX IX_LopHoc_HocVien_ThaoTac_HocVien
            ON dbo.LopHoc_HocVien_ThaoTac(HocVienId, NgayHieuLuc DESC);
    END;

    IF COL_LENGTH(N'dbo.DiemDanh_BuoiHoc', N'GhiChu') IS NULL
        ALTER TABLE dbo.DiemDanh_BuoiHoc ADD GhiChu NVARCHAR(1000) NULL;

    IF OBJECT_ID(N'dbo.DiemDanh_BuoiHoc_LichSu', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.DiemDanh_BuoiHoc_LichSu
        (
            LichSuId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_DiemDanh_BuoiHoc_LichSu PRIMARY KEY,
            LichHocId INT NOT NULL,
            HocVienId INT NOT NULL,
            TrangThaiCu NVARCHAR(30) NULL,
            TrangThaiMoi NVARCHAR(30) NULL,
            GhiChu NVARCHAR(1000) NULL,
            NguoiThucHienId INT NOT NULL,
            ThoiDiem DATETIME2 NOT NULL,
            CONSTRAINT FK_DiemDanh_BuoiHoc_LichSu_LichHoc
                FOREIGN KEY (LichHocId) REFERENCES dbo.LichHoc(LichHocId),
            CONSTRAINT FK_DiemDanh_BuoiHoc_LichSu_HocVien
                FOREIGN KEY (HocVienId) REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_DiemDanh_BuoiHoc_LichSu_NguoiThucHien
                FOREIGN KEY (NguoiThucHienId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );
        CREATE INDEX IX_DiemDanh_BuoiHoc_LichSu_LichHoc_ThoiDiem
            ON dbo.DiemDanh_BuoiHoc_LichSu(LichHocId, ThoiDiem DESC);
    END;

    IF OBJECT_ID(N'dbo.AssignmentNotification', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AssignmentNotification
        (
            NotificationId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_AssignmentNotification PRIMARY KEY,
            AssignmentId INT NOT NULL,
            NguoiNhanId INT NOT NULL,
            Loai VARCHAR(30) NOT NULL,
            TieuDe NVARCHAR(200) NOT NULL,
            NoiDung NVARCHAR(MAX) NOT NULL,
            NgayTao DATETIME2 NOT NULL,
            CONSTRAINT FK_AssignmentNotification_Assignment
                FOREIGN KEY (AssignmentId) REFERENCES dbo.Assignment(AssignmentId),
            CONSTRAINT FK_AssignmentNotification_NguoiNhan
                FOREIGN KEY (NguoiNhanId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );
        CREATE INDEX IX_AssignmentNotification_NguoiNhan_NgayTao
            ON dbo.AssignmentNotification(NguoiNhanId, NgayTao DESC);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
