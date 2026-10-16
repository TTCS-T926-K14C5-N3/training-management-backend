SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.LichHoc', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LichHoc (
            LichHocId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_LichHoc PRIMARY KEY,
            LopHocId INT NOT NULL,
            MonHocId INT NOT NULL,
            NgayHoc DATE NOT NULL,
            GioBatDau TIME(0) NOT NULL,
            GioKetThuc TIME(0) NOT NULL,
            PhongHocId INT NULL,
            GiangVienId INT NOT NULL,
            TrangThai NVARCHAR(20) NOT NULL
                CONSTRAINT DF_LichHoc_TrangThai DEFAULT N'Đã lên lịch',
            LyDoHuy NVARCHAR(1000) NULL,
            NgayTao DATETIME2 NOT NULL,
            NguoiTaoId INT NOT NULL,
            NgayCapNhat DATETIME2 NOT NULL,
            NguoiCapNhatId INT NOT NULL,
            NgayHuy DATETIME2 NULL,
            NguoiHuyId INT NULL,
            CONSTRAINT CK_LichHoc_Gio CHECK (GioKetThuc > GioBatDau),
            CONSTRAINT CK_LichHoc_TrangThai
                CHECK (TrangThai IN (N'Đã lên lịch', N'Đã hủy')),
            CONSTRAINT FK_LichHoc_LopHoc FOREIGN KEY (LopHocId)
                REFERENCES dbo.LopHoc(LopHocId),
            CONSTRAINT FK_LichHoc_MonHoc FOREIGN KEY (MonHocId)
                REFERENCES dbo.MonHoc(MonHocId),
            CONSTRAINT FK_LichHoc_PhongHoc FOREIGN KEY (PhongHocId)
                REFERENCES dbo.PhongHoc(PhongHocId),
            CONSTRAINT FK_LichHoc_GiangVien FOREIGN KEY (GiangVienId)
                REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_LichHoc_NguoiTao FOREIGN KEY (NguoiTaoId)
                REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_LichHoc_NguoiCapNhat FOREIGN KEY (NguoiCapNhatId)
                REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_LichHoc_NguoiHuy FOREIGN KEY (NguoiHuyId)
                REFERENCES dbo.NguoiDung(NguoiDungId)
        );

        CREATE INDEX IX_LichHoc_NgayHoc ON dbo.LichHoc(NgayHoc, TrangThai);
        CREATE INDEX IX_LichHoc_GiangVien_Lich
            ON dbo.LichHoc(GiangVienId, NgayHoc, TrangThai);
        CREATE INDEX IX_LichHoc_PhongHoc_Lich
            ON dbo.LichHoc(PhongHocId, NgayHoc, TrangThai);
    END;

    IF OBJECT_ID(N'dbo.LichHoc_LichSu', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LichHoc_LichSu (
            LichHocLichSuId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_LichHoc_LichSu PRIMARY KEY,
            LichHocId INT NOT NULL,
            HanhDong NVARCHAR(20) NOT NULL,
            DuLieuCu NVARCHAR(MAX) NULL,
            DuLieuMoi NVARCHAR(MAX) NULL,
            LyDo NVARCHAR(1000) NULL,
            ThoiDiem DATETIME2 NOT NULL,
            NguoiThucHienId INT NOT NULL,
            CONSTRAINT CK_LichHoc_LichSu_HanhDong
                CHECK (HanhDong IN (N'Tạo', N'Cập nhật', N'Hủy')),
            CONSTRAINT FK_LichHoc_LichSu_LichHoc FOREIGN KEY (LichHocId)
                REFERENCES dbo.LichHoc(LichHocId),
            CONSTRAINT FK_LichHoc_LichSu_NguoiDung FOREIGN KEY (NguoiThucHienId)
                REFERENCES dbo.NguoiDung(NguoiDungId)
        );

        CREATE INDEX IX_LichHoc_LichSu_ThoiDiem
            ON dbo.LichHoc_LichSu(ThoiDiem DESC);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
