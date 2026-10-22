SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.LichHoc_ThongBao', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LichHoc_ThongBao
        (
            LichHocThongBaoId INT IDENTITY(1,1) NOT NULL
                CONSTRAINT PK_LichHoc_ThongBao PRIMARY KEY,
            LichHocId INT NOT NULL,
            NguoiNhanId INT NOT NULL,
            TieuDe NVARCHAR(200) NOT NULL,
            NoiDung NVARCHAR(MAX) NOT NULL,
            ThoiDiem DATETIME2 NOT NULL,
            CONSTRAINT FK_LichHoc_ThongBao_LichHoc
                FOREIGN KEY (LichHocId) REFERENCES dbo.LichHoc(LichHocId),
            CONSTRAINT FK_LichHoc_ThongBao_NguoiNhan
                FOREIGN KEY (NguoiNhanId) REFERENCES dbo.NguoiDung(NguoiDungId)
        );

        CREATE INDEX IX_LichHoc_ThongBao_NguoiNhan_ThoiDiem
            ON dbo.LichHoc_ThongBao(NguoiNhanId, ThoiDiem DESC);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
