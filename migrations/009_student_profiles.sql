/*
    Persist additional student profile data and grant the training manager
    permission to maintain academic profiles. Safe to rerun.
*/
SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF COL_LENGTH(N'dbo.NguoiDung', N'TrinhDoDauVao') IS NULL
        ALTER TABLE dbo.NguoiDung ADD TrinhDoDauVao NVARCHAR(150) NULL;

    IF COL_LENGTH(N'dbo.NguoiDung', N'GhiChuHoSo') IS NULL
        ALTER TABLE dbo.NguoiDung ADD GhiChuHoSo NVARCHAR(2000) NULL;

    IF NOT EXISTS
    (
        SELECT 1 FROM dbo.Quyen WHERE MaQuyen = N'STUDENT_PROFILE_UPDATE'
    )
        INSERT INTO dbo.Quyen (MaQuyen, TenQuyen, MoTa)
        VALUES
        (
            N'STUDENT_PROFILE_UPDATE',
            N'Sửa hồ sơ học viên',
            N'Cập nhật thông tin cá nhân và ghi chú hồ sơ học viên.'
        );

    INSERT INTO dbo.VaiTro_Quyen (VaiTroId, QuyenId)
    SELECT roles.VaiTroId, q.QuyenId
    FROM (VALUES (7), (8)) AS roles(VaiTroId)
    INNER JOIN dbo.VaiTro AS r ON r.VaiTroId = roles.VaiTroId
    CROSS JOIN dbo.Quyen AS q
    WHERE q.MaQuyen = N'STUDENT_PROFILE_UPDATE'
      AND NOT EXISTS
      (
          SELECT 1
          FROM dbo.VaiTro_Quyen AS rq
          WHERE rq.VaiTroId = roles.VaiTroId
            AND rq.QuyenId = q.QuyenId
      );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
