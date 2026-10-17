SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF COL_LENGTH(N'dbo.LopHoc', N'HinhThuc') IS NULL
        ALTER TABLE dbo.LopHoc
            ADD HinhThuc NVARCHAR(20) NOT NULL
                CONSTRAINT DF_LopHoc_HinhThuc DEFAULT N'Trực tiếp';

    IF COL_LENGTH(N'dbo.LopHoc', N'PhongHocId') IS NULL
        ALTER TABLE dbo.LopHoc ADD PhongHocId INT NULL;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.foreign_keys
        WHERE name = N'FK_LopHoc_PhongHoc'
          AND parent_object_id = OBJECT_ID(N'dbo.LopHoc')
    )
        ALTER TABLE dbo.LopHoc
            ADD CONSTRAINT FK_LopHoc_PhongHoc
                FOREIGN KEY (PhongHocId)
                REFERENCES dbo.PhongHoc(PhongHocId);

    IF COL_LENGTH(N'dbo.LopHoc', N'LinkTrucTuyen') IS NULL
        ALTER TABLE dbo.LopHoc ADD LinkTrucTuyen NVARCHAR(500) NULL;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
