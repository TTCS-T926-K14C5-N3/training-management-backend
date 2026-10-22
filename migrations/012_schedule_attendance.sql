SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.DiemDanh_BuoiHoc', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.DiemDanh_BuoiHoc
        (
            DiemDanhBuoiHocId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_DiemDanh_BuoiHoc PRIMARY KEY,
            LichHocId INT NOT NULL,
            HocVienId INT NOT NULL,
            TrangThai NVARCHAR(30) NOT NULL,
            NgayCapNhat DATETIME2 NOT NULL,
            NguoiCapNhatId INT NOT NULL,
            CONSTRAINT UQ_DiemDanh_BuoiHoc_LichHoc_HocVien
                UNIQUE (LichHocId, HocVienId),
            CONSTRAINT CK_DiemDanh_BuoiHoc_TrangThai
                CHECK (TrangThai IN (N'Có mặt', N'Đi muộn', N'Vắng có phép', N'Vắng không phép')),
            CONSTRAINT FK_DiemDanh_BuoiHoc_LichHoc
                FOREIGN KEY (LichHocId) REFERENCES dbo.LichHoc(LichHocId),
            CONSTRAINT FK_DiemDanh_BuoiHoc_HocVien
                FOREIGN KEY (HocVienId) REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_DiemDanh_BuoiHoc_NguoiCapNhat
                FOREIGN KEY (NguoiCapNhatId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );
        CREATE INDEX IX_DiemDanh_BuoiHoc_HocVien
            ON dbo.DiemDanh_BuoiHoc(HocVienId, LichHocId);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
