SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.LichHoc', N'U') IS NULL
        THROW 50001, N'Chạy migration 010_class_schedules.sql trước.', 1;

    UPDATE schedule
    SET PhongHocId = class.PhongHocId
    FROM dbo.LichHoc AS schedule
    INNER JOIN dbo.LopHoc AS class
        ON class.LopHocId = schedule.LopHocId
    WHERE schedule.PhongHocId IS NULL
      AND class.PhongHocId IS NOT NULL;

    IF EXISTS (SELECT 1 FROM dbo.LichHoc WHERE PhongHocId IS NULL)
        THROW 50002, N'Có buổi học chưa được gán phòng. Hãy gán phòng rồi chạy lại migration.', 1;

    IF EXISTS
    (
        SELECT 1
        FROM sys.columns
        WHERE object_id = OBJECT_ID(N'dbo.LichHoc')
          AND name = N'PhongHocId'
          AND is_nullable = 1
    )
    BEGIN
        IF EXISTS
        (
            SELECT 1
            FROM sys.indexes
            WHERE object_id = OBJECT_ID(N'dbo.LichHoc')
              AND name = N'IX_LichHoc_PhongHoc_Lich'
        )
            DROP INDEX IX_LichHoc_PhongHoc_Lich ON dbo.LichHoc;

        ALTER TABLE dbo.LichHoc ALTER COLUMN PhongHocId INT NOT NULL;

        CREATE INDEX IX_LichHoc_PhongHoc_Lich
            ON dbo.LichHoc(PhongHocId, NgayHoc, TrangThai);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;