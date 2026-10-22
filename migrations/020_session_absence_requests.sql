SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.DonXinPhepVang', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.DonXinPhepVang
        (
            RequestId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_DonXinPhepVang PRIMARY KEY,
            LichHocId INT NOT NULL,
            HocVienId INT NOT NULL,
            LyDo NVARCHAR(1000) NOT NULL,
            TepMinhChungPath NVARCHAR(500) NULL,
            TepMinhChungTen NVARCHAR(255) NULL,
            TepMinhChungMime NVARCHAR(100) NULL,
            TepMinhChungKichThuoc INT NULL,
            TrangThai NVARCHAR(20) NOT NULL
                CONSTRAINT DF_DonXinPhepVang_TrangThai DEFAULT N'Chờ duyệt',
            LyDoDuyet NVARCHAR(1000) NULL,
            NguoiDuyetId INT NULL,
            ThoiDiemDuyet DATETIME2 NULL,
            NgayTao DATETIME2 NOT NULL,
            CONSTRAINT CK_DonXinPhepVang_TrangThai
                CHECK (TrangThai IN (N'Chờ duyệt', N'Đã duyệt', N'Từ chối')),
            CONSTRAINT UQ_DonXinPhepVang_LichHoc_HocVien
                UNIQUE (LichHocId, HocVienId),
            CONSTRAINT FK_DonXinPhepVang_LichHoc
                FOREIGN KEY (LichHocId) REFERENCES dbo.LichHoc(LichHocId),
            CONSTRAINT FK_DonXinPhepVang_HocVien
                FOREIGN KEY (HocVienId) REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_DonXinPhepVang_NguoiDuyet
                FOREIGN KEY (NguoiDuyetId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );

        CREATE INDEX IX_DonXinPhepVang_HocVien_TrangThai
            ON dbo.DonXinPhepVang(HocVienId, TrangThai, NgayTao);
        CREATE INDEX IX_DonXinPhepVang_LichHoc_TrangThai
            ON dbo.DonXinPhepVang(LichHocId, TrangThai);
    END;

    IF OBJECT_ID(N'dbo.DiemDanh_ThongBao', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.DiemDanh_ThongBao
        (
            NotificationId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_DiemDanh_ThongBao PRIMARY KEY,
            RequestId INT NOT NULL,
            NguoiNhanId INT NOT NULL,
            NoiDung NVARCHAR(MAX) NOT NULL,
            ThoiDiem DATETIME2 NOT NULL,
            DaDoc BIT NOT NULL
                CONSTRAINT DF_DiemDanh_ThongBao_DaDoc DEFAULT 0,
            CONSTRAINT FK_DiemDanh_ThongBao_Request
                FOREIGN KEY (RequestId)
                    REFERENCES dbo.DonXinPhepVang(RequestId),
            CONSTRAINT FK_DiemDanh_ThongBao_NguoiNhan
                FOREIGN KEY (NguoiNhanId)
                    REFERENCES dbo.NguoiDung(NguoiDungId)
        );

        CREATE INDEX IX_DiemDanh_ThongBao_NguoiNhan_ThoiDiem
            ON dbo.DiemDanh_ThongBao(NguoiNhanId, DaDoc, ThoiDiem DESC);
    END;

    IF OBJECT_ID(N'dbo.DiemDanh_BuoiHoc_XinPhep_LichSu', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.DiemDanh_BuoiHoc_XinPhep_LichSu
        (
            AuditId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_DiemDanh_BuoiHoc_XinPhep_LichSu PRIMARY KEY,
            LichHocId INT NOT NULL,
            HocVienId INT NOT NULL,
            TrangThaiCu NVARCHAR(30) NULL,
            TrangThaiMoi NVARCHAR(30) NOT NULL,
            GhiChu NVARCHAR(1000) NULL,
            NguoiThucHienId INT NOT NULL,
            ThoiDiem DATETIME2 NOT NULL,
            CONSTRAINT FK_DiemDanh_BuoiHoc_XinPhep_LichSu_LichHoc
                FOREIGN KEY (LichHocId) REFERENCES dbo.LichHoc(LichHocId),
            CONSTRAINT FK_DiemDanh_BuoiHoc_XinPhep_LichSu_HocVien
                FOREIGN KEY (HocVienId) REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_DiemDanh_BuoiHoc_XinPhep_LichSu_NguoiThucHien
                FOREIGN KEY (NguoiThucHienId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );

        CREATE INDEX IX_DiemDanh_BuoiHoc_XinPhep_LichSu_LichHoc_ThoiDiem
            ON dbo.DiemDanh_BuoiHoc_XinPhep_LichSu(LichHocId, ThoiDiem DESC);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
