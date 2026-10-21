SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.DiemDanh', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.DiemDanh
        (
            DiemDanhId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            LichHocId INT NOT NULL,
            HocVienId INT NOT NULL,
            TrangThai NVARCHAR(20) NOT NULL,
            GhiChu NVARCHAR(MAX) NULL,
            NguoiDiemDanhId INT NOT NULL,
            NgayCapNhat DATETIME2 NOT NULL,
            CONSTRAINT FK_DiemDanh_LichHoc
                FOREIGN KEY (LichHocId) REFERENCES dbo.LichHoc(LichHocId),
            CONSTRAINT FK_DiemDanh_HocVien
                FOREIGN KEY (HocVienId) REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_DiemDanh_NguoiDiemDanh
                FOREIGN KEY (NguoiDiemDanhId) REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT UQ_DiemDanh_LichHoc_HocVien
                UNIQUE (LichHocId, HocVienId),
            CONSTRAINT CK_DiemDanh_TrangThai
                CHECK (TrangThai IN (N'Có mặt', N'Vắng', N'Muộn', N'Có phép'))
        );

        CREATE INDEX IX_DiemDanh_HocVien_LichHoc
            ON dbo.DiemDanh(HocVienId, LichHocId);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;