SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.LichHoc_ThongBao', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LichHoc_ThongBao
        (
            LichHocThongBaoId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_LichHoc_ThongBao PRIMARY KEY,
            SuKienId NVARCHAR(36) NOT NULL,
            LichHocId INT NOT NULL,
            NguoiNhanId INT NOT NULL,
            LoaiSuKien NVARCHAR(30) NOT NULL,
            NoiDung NVARCHAR(MAX) NOT NULL,
            DuLieuCu NVARCHAR(MAX) NOT NULL,
            DuLieuMoi NVARCHAR(MAX) NOT NULL,
            LyDo NVARCHAR(1000) NULL,
            NguoiThucHienId INT NOT NULL,
            ThoiDiemPhatSinh DATETIME2 NOT NULL,
            TrangThai NVARCHAR(20) NOT NULL
                CONSTRAINT DF_LichHoc_ThongBao_TrangThai
                DEFAULT N'Chờ gửi',
            SoLanGui INT NOT NULL
                CONSTRAINT DF_LichHoc_ThongBao_SoLanGui DEFAULT 0,
            ThoiDiemGuiCuoi DATETIME2 NULL,
            ThoiDiemGui DATETIME2 NULL,
            LoiGui NVARCHAR(2000) NULL,
            CONSTRAINT UQ_LichHoc_ThongBao_SuKien_NguoiNhan
                UNIQUE (SuKienId, NguoiNhanId),
            CONSTRAINT CK_LichHoc_ThongBao_TrangThai
                CHECK (TrangThai IN
                    (N'Chờ gửi', N'Đang gửi', N'Đã gửi', N'Thất bại')),
            CONSTRAINT FK_LichHoc_ThongBao_LichHoc
                FOREIGN KEY (LichHocId) REFERENCES dbo.LichHoc(LichHocId),
            CONSTRAINT FK_LichHoc_ThongBao_NguoiNhan
                FOREIGN KEY (NguoiNhanId) REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_LichHoc_ThongBao_NguoiThucHien
                FOREIGN KEY (NguoiThucHienId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );

        CREATE INDEX IX_LichHoc_ThongBao_TrangThai
            ON dbo.LichHoc_ThongBao(TrangThai, LichHocThongBaoId);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
