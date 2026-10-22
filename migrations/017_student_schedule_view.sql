SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF EXISTS (
        SELECT 1
        FROM dbo.VaiTro
        WHERE VaiTroId = 2
    )
    AND EXISTS (
        SELECT 1
        FROM dbo.Quyen
        WHERE MaQuyen = N'SCHEDULE_VIEW'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM dbo.VaiTro_Quyen role_permission
        INNER JOIN dbo.Quyen permission
            ON permission.QuyenId = role_permission.QuyenId
        WHERE role_permission.VaiTroId = 2
            AND permission.MaQuyen = N'SCHEDULE_VIEW'
    )
    BEGIN
        INSERT INTO dbo.VaiTro_Quyen (VaiTroId, QuyenId)
        SELECT 2, QuyenId
        FROM dbo.Quyen
        WHERE MaQuyen = N'SCHEDULE_VIEW';
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
