SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF COL_LENGTH(N'dbo.LichHoc', N'BuoiHocId') IS NULL
    BEGIN
        EXEC sys.sp_executesql
            N'ALTER TABLE dbo.LichHoc ADD BuoiHocId INT NULL;';
        EXEC sys.sp_executesql
            N'ALTER TABLE dbo.LichHoc
                ADD CONSTRAINT FK_LichHoc_BuoiHoc
                FOREIGN KEY (BuoiHocId) REFERENCES dbo.BuoiHoc(BuoiHocId);';
        EXEC sys.sp_executesql
            N'CREATE UNIQUE INDEX UX_LichHoc_LopHoc_BuoiHoc_DaLenLich
                ON dbo.LichHoc(LopHocId, BuoiHocId)
                WHERE BuoiHocId IS NOT NULL
                  AND TrangThai = N''Đã lên lịch'';';
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
