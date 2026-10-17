SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF COL_LENGTH(N'dbo.PhongHoc', N'LoaiPhong') IS NULL
        ALTER TABLE dbo.PhongHoc
        ADD LoaiPhong NVARCHAR(20) NOT NULL
            CONSTRAINT DF_PhongHoc_LoaiPhong DEFAULT N'Trực tiếp'
            WITH VALUES;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'dbo.PhongHoc')
          AND name = N'CK_PhongHoc_LoaiPhong'
    )
        ALTER TABLE dbo.PhongHoc
        ADD CONSTRAINT CK_PhongHoc_LoaiPhong
            CHECK (LoaiPhong IN (N'Trực tiếp', N'Trực tuyến'));

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
