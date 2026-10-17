SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.DiemDanh', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.DiemDanh (
            DiemDanhId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_DiemDanh PRIMARY KEY,
            LopHocId INT NOT NULL,
            HocVienId INT NOT NULL,
            NgayHoc DATE NOT NULL,
            TrangThai NVARCHAR(30) NOT NULL,
            GhiChu NVARCHAR(MAX) NULL,
            NguoiCapNhatId INT NOT NULL,
            NgayCapNhat DATETIME2 NOT NULL,
            CONSTRAINT UQ_DiemDanh_Lop_HocVien_Ngay UNIQUE (LopHocId, HocVienId, NgayHoc),
            CONSTRAINT CK_DiemDanh_TrangThai CHECK (TrangThai IN ('present', 'late', 'excused_absence', 'unexcused_absence')),
            CONSTRAINT FK_DiemDanh_Lop FOREIGN KEY (LopHocId) REFERENCES dbo.LopHoc(LopHocId),
            CONSTRAINT FK_DiemDanh_HocVien FOREIGN KEY (HocVienId) REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_DiemDanh_NguoiCapNhat FOREIGN KEY (NguoiCapNhatId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );
        CREATE INDEX IX_DiemDanh_Ngay_Lop ON dbo.DiemDanh(NgayHoc, LopHocId);
        CREATE INDEX IX_DiemDanh_HocVien_Ngay ON dbo.DiemDanh(HocVienId, NgayHoc DESC);
    END;

    IF OBJECT_ID(N'dbo.DonXinVang', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.DonXinVang (
            DonXinVangId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_DonXinVang PRIMARY KEY,
            LopHocId INT NOT NULL,
            HocVienId INT NOT NULL,
            NgayHoc DATE NOT NULL,
            LyDo NVARCHAR(2000) NOT NULL,
            TepChungMinh NVARCHAR(1000) NULL,
            TrangThai NVARCHAR(20) NOT NULL CONSTRAINT DF_DonXinVang_TrangThai DEFAULT 'pending',
            LyDoXuLy NVARCHAR(1000) NULL,
            NguoiXuLyId INT NULL,
            NgayXuLy DATETIME2 NULL,
            NgayTao DATETIME2 NOT NULL,
            CONSTRAINT CK_DonXinVang_TrangThai CHECK (TrangThai IN ('pending', 'approved', 'rejected')),
            CONSTRAINT FK_DonXinVang_Lop FOREIGN KEY (LopHocId) REFERENCES dbo.LopHoc(LopHocId),
            CONSTRAINT FK_DonXinVang_HocVien FOREIGN KEY (HocVienId) REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_DonXinVang_NguoiXuLy FOREIGN KEY (NguoiXuLyId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );
        CREATE INDEX IX_DonXinVang_TrangThai_Ngay ON dbo.DonXinVang(TrangThai, NgayHoc);
    END;

    IF OBJECT_ID(N'dbo.DiemDanh_LichSu', N'U') IS NULL
        CREATE TABLE dbo.DiemDanh_LichSu (
            LichSuId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_DiemDanh_LichSu PRIMARY KEY,
            DoiTuong NVARCHAR(30) NOT NULL,
            DoiTuongId INT NOT NULL,
            HanhDong NVARCHAR(30) NOT NULL,
            DuLieuCu NVARCHAR(MAX) NULL,
            DuLieuMoi NVARCHAR(MAX) NULL,
            LyDo NVARCHAR(1000) NULL,
            ThoiDiem DATETIME2 NOT NULL,
            NguoiThucHienId INT NOT NULL,
            CONSTRAINT FK_DiemDanh_LichSu_NguoiDung FOREIGN KEY (NguoiThucHienId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );

    IF OBJECT_ID(N'dbo.NguongVang', N'U') IS NULL
        CREATE TABLE dbo.NguongVang (
            ChuongTrinhId INT NOT NULL CONSTRAINT PK_NguongVang PRIMARY KEY,
            TiLeToiDa INT NOT NULL CONSTRAINT DF_NguongVang_TiLe DEFAULT 20,
            NguoiCapNhatId INT NULL,
            NgayCapNhat DATETIME2 NOT NULL,
            CONSTRAINT CK_NguongVang_TiLe CHECK (TiLeToiDa BETWEEN 0 AND 100),
            CONSTRAINT FK_NguongVang_ChuongTrinh FOREIGN KEY (ChuongTrinhId) REFERENCES dbo.ChuongTrinhDaoTao(ChuongTrinhId),
            CONSTRAINT FK_NguongVang_NguoiDung FOREIGN KEY (NguoiCapNhatId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );

    IF OBJECT_ID(N'dbo.ThongBaoDiemDanh', N'U') IS NULL
        CREATE TABLE dbo.ThongBaoDiemDanh (
            ThongBaoId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ThongBaoDiemDanh PRIMARY KEY,
            NguoiNhanId INT NOT NULL,
            HocVienId INT NULL,
            ChuongTrinhId INT NULL,
            Loai NVARCHAR(40) NOT NULL,
            TieuDe NVARCHAR(200) NOT NULL,
            NoiDung NVARCHAR(1000) NOT NULL,
            ThoiDiem DATETIME2 NOT NULL,
            DaDoc DATETIME2 NULL,
            CONSTRAINT FK_ThongBaoDiemDanh_NguoiNhan FOREIGN KEY (NguoiNhanId) REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_ThongBaoDiemDanh_HocVien FOREIGN KEY (HocVienId) REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_ThongBaoDiemDanh_ChuongTrinh FOREIGN KEY (ChuongTrinhId) REFERENCES dbo.ChuongTrinhDaoTao(ChuongTrinhId)
        );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
