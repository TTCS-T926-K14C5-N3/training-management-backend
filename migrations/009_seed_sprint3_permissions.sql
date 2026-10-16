/*
    Sprint 3 – seed missing permissions into the Quyen table and assign them
    to the correct roles.  Safe to run repeatedly (all inserts are guarded).
    Run AFTER 008_sprint_3.sql.
*/
SET ANSI_NULLS ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET ARITHABORT ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET QUOTED_IDENTIFIER ON;
SET NUMERIC_ROUNDABORT OFF;
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    -- -------------------------------------------------------
    -- 1. Ensure every Sprint-3 permission exists in dbo.Quyen
    -- -------------------------------------------------------
    IF NOT EXISTS (SELECT 1 FROM dbo.Quyen WHERE MaQuyen = N'CURRICULUM_VIEW')
        INSERT INTO dbo.Quyen (MaQuyen, TenQuyen, MoTa)
        VALUES (N'CURRICULUM_VIEW', N'Xem danh mục đào tạo', N'Xem môn học và cấu trúc chương trình.');

    IF NOT EXISTS (SELECT 1 FROM dbo.Quyen WHERE MaQuyen = N'CURRICULUM_CREATE')
        INSERT INTO dbo.Quyen (MaQuyen, TenQuyen, MoTa)
        VALUES (N'CURRICULUM_CREATE', N'Tạo danh mục đào tạo', N'Tạo môn học trong danh mục đào tạo.');

    IF NOT EXISTS (SELECT 1 FROM dbo.Quyen WHERE MaQuyen = N'CURRICULUM_UPDATE')
        INSERT INTO dbo.Quyen (MaQuyen, TenQuyen, MoTa)
        VALUES (N'CURRICULUM_UPDATE', N'Sửa danh mục đào tạo', N'Sửa môn học và cấu trúc chương trình.');

    IF NOT EXISTS (SELECT 1 FROM dbo.Quyen WHERE MaQuyen = N'CURRICULUM_DELETE')
        INSERT INTO dbo.Quyen (MaQuyen, TenQuyen, MoTa)
        VALUES (N'CURRICULUM_DELETE', N'Lưu trữ danh mục đào tạo', N'Lưu trữ môn học trong danh mục đào tạo.');

    IF NOT EXISTS (SELECT 1 FROM dbo.Quyen WHERE MaQuyen = N'LEAD_VIEW')
        INSERT INTO dbo.Quyen (MaQuyen, TenQuyen, MoTa)
        VALUES (N'LEAD_VIEW', N'Xem khách hàng tiềm năng', N'Xem hồ sơ tuyển sinh được phép truy cập.');

    IF NOT EXISTS (SELECT 1 FROM dbo.Quyen WHERE MaQuyen = N'LEAD_CREATE')
        INSERT INTO dbo.Quyen (MaQuyen, TenQuyen, MoTa)
        VALUES (N'LEAD_CREATE', N'Tạo khách hàng tiềm năng', N'Tạo hồ sơ khách hàng tiềm năng.');

    IF NOT EXISTS (SELECT 1 FROM dbo.Quyen WHERE MaQuyen = N'LEAD_UPDATE')
        INSERT INTO dbo.Quyen (MaQuyen, TenQuyen, MoTa)
        VALUES (N'LEAD_UPDATE', N'Sửa khách hàng tiềm năng', N'Cập nhật hồ sơ khách hàng tiềm năng.');

    IF NOT EXISTS (SELECT 1 FROM dbo.Quyen WHERE MaQuyen = N'LEAD_DELETE')
        INSERT INTO dbo.Quyen (MaQuyen, TenQuyen, MoTa)
        VALUES (N'LEAD_DELETE', N'Xóa khách hàng tiềm năng', N'Xóa hồ sơ khách hàng tiềm năng.');

    IF NOT EXISTS (SELECT 1 FROM dbo.Quyen WHERE MaQuyen = N'LEAD_ASSIGN')
        INSERT INTO dbo.Quyen (MaQuyen, TenQuyen, MoTa)
        VALUES (N'LEAD_ASSIGN', N'Phân công tư vấn', N'Phân công khách hàng tiềm năng cho tư vấn viên.');

    -- -------------------------------------------------------
    -- 2. Helper: assign a permission to a role if not already assigned
    -- -------------------------------------------------------
    -- Role 3 – Giảng viên: CURRICULUM_VIEW
    IF NOT EXISTS (
        SELECT 1 FROM dbo.VaiTro_Quyen vq
        INNER JOIN dbo.Quyen q ON q.QuyenId = vq.QuyenId
        WHERE vq.VaiTroId = 3 AND q.MaQuyen = N'CURRICULUM_VIEW'
    )
        INSERT INTO dbo.VaiTro_Quyen (VaiTroId, QuyenId)
        SELECT 3, QuyenId FROM dbo.Quyen WHERE MaQuyen = N'CURRICULUM_VIEW';

    -- Role 5 – Tuyển sinh: LEAD_VIEW, LEAD_CREATE, LEAD_UPDATE, USER_VIEW, USER_CREATE, USER_UPDATE
    IF NOT EXISTS (
        SELECT 1 FROM dbo.VaiTro_Quyen vq
        INNER JOIN dbo.Quyen q ON q.QuyenId = vq.QuyenId
        WHERE vq.VaiTroId = 5 AND q.MaQuyen = N'LEAD_VIEW'
    )
        INSERT INTO dbo.VaiTro_Quyen (VaiTroId, QuyenId)
        SELECT 5, QuyenId FROM dbo.Quyen WHERE MaQuyen = N'LEAD_VIEW';

    IF NOT EXISTS (
        SELECT 1 FROM dbo.VaiTro_Quyen vq
        INNER JOIN dbo.Quyen q ON q.QuyenId = vq.QuyenId
        WHERE vq.VaiTroId = 5 AND q.MaQuyen = N'LEAD_CREATE'
    )
        INSERT INTO dbo.VaiTro_Quyen (VaiTroId, QuyenId)
        SELECT 5, QuyenId FROM dbo.Quyen WHERE MaQuyen = N'LEAD_CREATE';

    IF NOT EXISTS (
        SELECT 1 FROM dbo.VaiTro_Quyen vq
        INNER JOIN dbo.Quyen q ON q.QuyenId = vq.QuyenId
        WHERE vq.VaiTroId = 5 AND q.MaQuyen = N'LEAD_UPDATE'
    )
        INSERT INTO dbo.VaiTro_Quyen (VaiTroId, QuyenId)
        SELECT 5, QuyenId FROM dbo.Quyen WHERE MaQuyen = N'LEAD_UPDATE';

    IF NOT EXISTS (
        SELECT 1 FROM dbo.VaiTro_Quyen vq
        INNER JOIN dbo.Quyen q ON q.QuyenId = vq.QuyenId
        WHERE vq.VaiTroId = 5 AND q.MaQuyen = N'USER_VIEW'
    )
        INSERT INTO dbo.VaiTro_Quyen (VaiTroId, QuyenId)
        SELECT 5, QuyenId FROM dbo.Quyen WHERE MaQuyen = N'USER_VIEW';

    IF NOT EXISTS (
        SELECT 1 FROM dbo.VaiTro_Quyen vq
        INNER JOIN dbo.Quyen q ON q.QuyenId = vq.QuyenId
        WHERE vq.VaiTroId = 5 AND q.MaQuyen = N'USER_CREATE'
    )
        INSERT INTO dbo.VaiTro_Quyen (VaiTroId, QuyenId)
        SELECT 5, QuyenId FROM dbo.Quyen WHERE MaQuyen = N'USER_CREATE';

    IF NOT EXISTS (
        SELECT 1 FROM dbo.VaiTro_Quyen vq
        INNER JOIN dbo.Quyen q ON q.QuyenId = vq.QuyenId
        WHERE vq.VaiTroId = 5 AND q.MaQuyen = N'USER_UPDATE'
    )
        INSERT INTO dbo.VaiTro_Quyen (VaiTroId, QuyenId)
        SELECT 5, QuyenId FROM dbo.Quyen WHERE MaQuyen = N'USER_UPDATE';

    -- Role 7 – Quản lý đào tạo: full curriculum + lead permissions
    DECLARE @role7Perms TABLE (MaQuyen NVARCHAR(50));
    INSERT INTO @role7Perms VALUES
        (N'USER_VIEW'), (N'ROLE_VIEW'),
        (N'GRADE_VIEW'), (N'TUITION_VIEW'),
        (N'CLASS_VIEW'), (N'CLASS_CREATE'), (N'CLASS_UPDATE'), (N'CLASS_DELETE'), (N'QUAN_LY_LOP'),
        (N'CURRICULUM_VIEW'), (N'CURRICULUM_CREATE'), (N'CURRICULUM_UPDATE'), (N'CURRICULUM_DELETE'),
        (N'LEAD_VIEW'), (N'LEAD_CREATE'), (N'LEAD_UPDATE'), (N'LEAD_DELETE'), (N'LEAD_ASSIGN');

    INSERT INTO dbo.VaiTro_Quyen (VaiTroId, QuyenId)
    SELECT 7, q.QuyenId
    FROM dbo.Quyen q
    INNER JOIN @role7Perms p ON p.MaQuyen = q.MaQuyen
    WHERE NOT EXISTS (
        SELECT 1 FROM dbo.VaiTro_Quyen vq
        WHERE vq.VaiTroId = 7 AND vq.QuyenId = q.QuyenId
    );

    -- Role 8 – Quản trị hệ thống: ALL permissions
    INSERT INTO dbo.VaiTro_Quyen (VaiTroId, QuyenId)
    SELECT 8, q.QuyenId
    FROM dbo.Quyen q
    WHERE NOT EXISTS (
        SELECT 1 FROM dbo.VaiTro_Quyen vq
        WHERE vq.VaiTroId = 8 AND vq.QuyenId = q.QuyenId
    );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
