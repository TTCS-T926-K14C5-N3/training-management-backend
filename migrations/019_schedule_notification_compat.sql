SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.LichHoc_ThongBao', N'U') IS NULL
        THROW 51000, 'Migration 019 requires dbo.LichHoc_ThongBao.', 1;

    IF COL_LENGTH(N'dbo.LichHoc_ThongBao', N'SuKienId') IS NULL
        ALTER TABLE dbo.LichHoc_ThongBao ADD SuKienId NVARCHAR(36) NULL;
    IF COL_LENGTH(N'dbo.LichHoc_ThongBao', N'LoaiSuKien') IS NULL
        ALTER TABLE dbo.LichHoc_ThongBao ADD LoaiSuKien NVARCHAR(30) NULL;
    IF COL_LENGTH(N'dbo.LichHoc_ThongBao', N'DuLieuCu') IS NULL
        ALTER TABLE dbo.LichHoc_ThongBao ADD DuLieuCu NVARCHAR(MAX) NULL;
    IF COL_LENGTH(N'dbo.LichHoc_ThongBao', N'DuLieuMoi') IS NULL
        ALTER TABLE dbo.LichHoc_ThongBao ADD DuLieuMoi NVARCHAR(MAX) NULL;
    IF COL_LENGTH(N'dbo.LichHoc_ThongBao', N'LyDo') IS NULL
        ALTER TABLE dbo.LichHoc_ThongBao ADD LyDo NVARCHAR(1000) NULL;
    IF COL_LENGTH(N'dbo.LichHoc_ThongBao', N'NguoiThucHienId') IS NULL
        ALTER TABLE dbo.LichHoc_ThongBao ADD NguoiThucHienId INT NULL;
    IF COL_LENGTH(N'dbo.LichHoc_ThongBao', N'ThoiDiemPhatSinh') IS NULL
        ALTER TABLE dbo.LichHoc_ThongBao ADD ThoiDiemPhatSinh DATETIME2 NULL;
    IF COL_LENGTH(N'dbo.LichHoc_ThongBao', N'TrangThai') IS NULL
        ALTER TABLE dbo.LichHoc_ThongBao
            ADD TrangThai NVARCHAR(20) NULL
                CONSTRAINT DF_LichHoc_ThongBao_Compat_TrangThai
                DEFAULT N'Đã gửi';
    IF COL_LENGTH(N'dbo.LichHoc_ThongBao', N'SoLanGui') IS NULL
        ALTER TABLE dbo.LichHoc_ThongBao
            ADD SoLanGui INT NULL
                CONSTRAINT DF_LichHoc_ThongBao_Compat_SoLanGui DEFAULT 0;
    IF COL_LENGTH(N'dbo.LichHoc_ThongBao', N'ThoiDiemGuiCuoi') IS NULL
        ALTER TABLE dbo.LichHoc_ThongBao ADD ThoiDiemGuiCuoi DATETIME2 NULL;
    IF COL_LENGTH(N'dbo.LichHoc_ThongBao', N'ThoiDiemGui') IS NULL
        ALTER TABLE dbo.LichHoc_ThongBao ADD ThoiDiemGui DATETIME2 NULL;
    IF COL_LENGTH(N'dbo.LichHoc_ThongBao', N'LoiGui') IS NULL
        ALTER TABLE dbo.LichHoc_ThongBao ADD LoiGui NVARCHAR(2000) NULL;

    UPDATE dbo.LichHoc_ThongBao
    SET SuKienId = COALESCE(SuKienId, CONVERT(NVARCHAR(36), NEWID())),
        LoaiSuKien = COALESCE(LoaiSuKien, N'Thay đổi lịch'),
        DuLieuCu = COALESCE(DuLieuCu, N'{}'),
        DuLieuMoi = COALESCE(DuLieuMoi, N'{}'),
        TrangThai = COALESCE(TrangThai, N'Đã gửi'),
        SoLanGui = COALESCE(SoLanGui, 0);

    IF COL_LENGTH(N'dbo.LichHoc_ThongBao', N'ThoiDiem') IS NOT NULL
        EXEC sys.sp_executesql N'
            UPDATE dbo.LichHoc_ThongBao
            SET ThoiDiemPhatSinh = COALESCE(ThoiDiemPhatSinh, ThoiDiem);';
    ELSE
        UPDATE dbo.LichHoc_ThongBao
        SET ThoiDiemPhatSinh = COALESCE(
            ThoiDiemPhatSinh,
            SYSUTCDATETIME()
        );

    ALTER TABLE dbo.LichHoc_ThongBao
        ALTER COLUMN SuKienId NVARCHAR(36) NOT NULL;
    ALTER TABLE dbo.LichHoc_ThongBao
        ALTER COLUMN LoaiSuKien NVARCHAR(30) NOT NULL;
    ALTER TABLE dbo.LichHoc_ThongBao
        ALTER COLUMN DuLieuCu NVARCHAR(MAX) NOT NULL;
    ALTER TABLE dbo.LichHoc_ThongBao
        ALTER COLUMN DuLieuMoi NVARCHAR(MAX) NOT NULL;
    ALTER TABLE dbo.LichHoc_ThongBao
        ALTER COLUMN ThoiDiemPhatSinh DATETIME2 NOT NULL;
    ALTER TABLE dbo.LichHoc_ThongBao
        ALTER COLUMN TrangThai NVARCHAR(20) NOT NULL;
    ALTER TABLE dbo.LichHoc_ThongBao
        ALTER COLUMN SoLanGui INT NOT NULL;

    IF NOT EXISTS (
        SELECT 1 FROM sys.key_constraints
        WHERE name = N'UQ_LichHoc_ThongBao_SuKien_NguoiNhan'
            AND parent_object_id = OBJECT_ID(N'dbo.LichHoc_ThongBao')
    )
        ALTER TABLE dbo.LichHoc_ThongBao
            ADD CONSTRAINT UQ_LichHoc_ThongBao_SuKien_NguoiNhan
                UNIQUE (SuKienId, NguoiNhanId);

    IF NOT EXISTS (
        SELECT 1 FROM sys.foreign_keys
        WHERE name = N'FK_LichHoc_ThongBao_NguoiThucHien'
            AND parent_object_id = OBJECT_ID(N'dbo.LichHoc_ThongBao')
    )
        ALTER TABLE dbo.LichHoc_ThongBao
            ADD CONSTRAINT FK_LichHoc_ThongBao_NguoiThucHien
                FOREIGN KEY (NguoiThucHienId)
                REFERENCES dbo.NguoiDung(NguoiDungId);

    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE name = N'IX_LichHoc_ThongBao_TrangThai'
            AND object_id = OBJECT_ID(N'dbo.LichHoc_ThongBao')
    )
        CREATE INDEX IX_LichHoc_ThongBao_TrangThai
            ON dbo.LichHoc_ThongBao(TrangThai, LichHocThongBaoId);

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
