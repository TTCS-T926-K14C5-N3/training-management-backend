/*
    Align default permissions with role names in databases created with the
    legacy role ID order. Safe to rerun; unrelated/custom grants are preserved.
*/
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    DECLARE @AdminRoleId INT;
    DECLARE @ManagerRoleId INT;
    DECLARE @TeacherRoleId INT;
    DECLARE @AdmissionsRoleId INT;
    DECLARE @AccountantRoleId INT;
    DECLARE @StudentRoleId INT;

    SELECT @AdminRoleId = VaiTroId
    FROM dbo.VaiTro
    WHERE TenVaiTro IN (N'Quản trị hệ thống', N'Quản trị viên hệ thống');

    SELECT @ManagerRoleId = VaiTroId
    FROM dbo.VaiTro
    WHERE TenVaiTro = N'Quản lý đào tạo';

    SELECT @TeacherRoleId = VaiTroId
    FROM dbo.VaiTro
    WHERE TenVaiTro = N'Giảng viên';

    SELECT @AdmissionsRoleId = VaiTroId
    FROM dbo.VaiTro
    WHERE TenVaiTro IN (N'Tuyển sinh', N'Nhân viên tuyển sinh');

    SELECT @AccountantRoleId = VaiTroId
    FROM dbo.VaiTro
    WHERE TenVaiTro = N'Kế toán';

    SELECT @StudentRoleId = VaiTroId
    FROM dbo.VaiTro
    WHERE TenVaiTro IN (N'Sinh viên', N'Học viên');

    IF @AdminRoleId IS NULL
        THROW 50009, 'System administrator role was not found.', 1;

    DECLARE @PermissionCatalog TABLE (MaQuyen NVARCHAR(50) PRIMARY KEY);
    INSERT INTO @PermissionCatalog (MaQuyen)
    VALUES
        (N'USER_VIEW'), (N'USER_CREATE'), (N'USER_UPDATE'),
        (N'USER_LOCK'), (N'USER_UNLOCK'), (N'USER_DELETE'),
        (N'ROLE_VIEW'), (N'ROLE_UPDATE'), (N'ROLE_DELETE'),
        (N'GRADE_VIEW'), (N'GRADE_CREATE'), (N'GRADE_UPDATE'),
        (N'GRADE_DELETE'), (N'QUAN_LY_DIEM'),
        (N'TUITION_VIEW'), (N'TUITION_CREATE'), (N'TUITION_UPDATE'),
        (N'TUITION_DELETE'), (N'QUAN_LY_HOC_PHI'),
        (N'CLASS_VIEW'), (N'CLASS_CREATE'), (N'CLASS_UPDATE'),
        (N'CLASS_DELETE'), (N'QUAN_LY_LOP'),
        (N'CURRICULUM_VIEW'), (N'CURRICULUM_CREATE'),
        (N'CURRICULUM_UPDATE'), (N'CURRICULUM_DELETE'),
        (N'LEAD_VIEW'), (N'LEAD_CREATE'), (N'LEAD_UPDATE'),
        (N'LEAD_DELETE'), (N'LEAD_ASSIGN');

    DECLARE @MisassignedGrants TABLE
    (
        VaiTroId INT NOT NULL,
        MaQuyen NVARCHAR(50) NOT NULL
    );

    IF @AdminRoleId <> 8
        INSERT INTO @MisassignedGrants (VaiTroId, MaQuyen)
        SELECT 8, MaQuyen FROM @PermissionCatalog;

    IF @ManagerRoleId IS NOT NULL AND @ManagerRoleId <> 7
        INSERT INTO @MisassignedGrants (VaiTroId, MaQuyen)
        VALUES
            (7, N'USER_VIEW'), (7, N'ROLE_VIEW'), (7, N'GRADE_VIEW'),
            (7, N'TUITION_VIEW'), (7, N'CLASS_VIEW'), (7, N'CLASS_CREATE'),
            (7, N'CLASS_UPDATE'), (7, N'CLASS_DELETE'), (7, N'QUAN_LY_LOP'),
            (7, N'CURRICULUM_VIEW'), (7, N'CURRICULUM_CREATE'),
            (7, N'CURRICULUM_UPDATE'), (7, N'CURRICULUM_DELETE'),
            (7, N'LEAD_VIEW'), (7, N'LEAD_CREATE'), (7, N'LEAD_UPDATE'),
            (7, N'LEAD_DELETE'), (7, N'LEAD_ASSIGN');

    IF @AccountantRoleId IS NOT NULL AND @AccountantRoleId <> 6
        INSERT INTO @MisassignedGrants (VaiTroId, MaQuyen)
        VALUES
            (6, N'TUITION_VIEW'), (6, N'TUITION_CREATE'),
            (6, N'TUITION_UPDATE'), (6, N'QUAN_LY_HOC_PHI');

    IF @StudentRoleId IS NOT NULL AND @StudentRoleId <> 2
        INSERT INTO @MisassignedGrants (VaiTroId, MaQuyen)
        VALUES (2, N'GRADE_VIEW'), (2, N'TUITION_VIEW');

    DELETE role_permission
    FROM dbo.VaiTro_Quyen AS role_permission
    INNER JOIN dbo.Quyen AS permission
        ON permission.QuyenId = role_permission.QuyenId
    INNER JOIN @MisassignedGrants AS misplaced
        ON misplaced.VaiTroId = role_permission.VaiTroId
       AND misplaced.MaQuyen = permission.MaQuyen;

    DECLARE @DefaultGrants TABLE
    (
        VaiTroId INT NOT NULL,
        MaQuyen NVARCHAR(50) NOT NULL
    );

    INSERT INTO @DefaultGrants (VaiTroId, MaQuyen)
    SELECT @AdminRoleId, MaQuyen FROM @PermissionCatalog;

    IF @ManagerRoleId IS NOT NULL
        INSERT INTO @DefaultGrants (VaiTroId, MaQuyen)
        VALUES
            (@ManagerRoleId, N'USER_VIEW'), (@ManagerRoleId, N'ROLE_VIEW'),
            (@ManagerRoleId, N'GRADE_VIEW'), (@ManagerRoleId, N'TUITION_VIEW'),
            (@ManagerRoleId, N'CLASS_VIEW'), (@ManagerRoleId, N'CLASS_CREATE'),
            (@ManagerRoleId, N'CLASS_UPDATE'), (@ManagerRoleId, N'CLASS_DELETE'),
            (@ManagerRoleId, N'QUAN_LY_LOP'),
            (@ManagerRoleId, N'CURRICULUM_VIEW'),
            (@ManagerRoleId, N'CURRICULUM_CREATE'),
            (@ManagerRoleId, N'CURRICULUM_UPDATE'),
            (@ManagerRoleId, N'CURRICULUM_DELETE'),
            (@ManagerRoleId, N'LEAD_VIEW'), (@ManagerRoleId, N'LEAD_CREATE'),
            (@ManagerRoleId, N'LEAD_UPDATE'), (@ManagerRoleId, N'LEAD_DELETE'),
            (@ManagerRoleId, N'LEAD_ASSIGN');

    IF @TeacherRoleId IS NOT NULL
        INSERT INTO @DefaultGrants (VaiTroId, MaQuyen)
        VALUES
            (@TeacherRoleId, N'GRADE_VIEW'), (@TeacherRoleId, N'GRADE_CREATE'),
            (@TeacherRoleId, N'GRADE_UPDATE'), (@TeacherRoleId, N'QUAN_LY_DIEM'),
            (@TeacherRoleId, N'CLASS_VIEW'), (@TeacherRoleId, N'CURRICULUM_VIEW');

    IF @AdmissionsRoleId IS NOT NULL
        INSERT INTO @DefaultGrants (VaiTroId, MaQuyen)
        VALUES
            (@AdmissionsRoleId, N'USER_VIEW'),
            (@AdmissionsRoleId, N'USER_CREATE'),
            (@AdmissionsRoleId, N'USER_UPDATE'),
            (@AdmissionsRoleId, N'LEAD_VIEW'),
            (@AdmissionsRoleId, N'LEAD_CREATE'),
            (@AdmissionsRoleId, N'LEAD_UPDATE');

    IF @AccountantRoleId IS NOT NULL
        INSERT INTO @DefaultGrants (VaiTroId, MaQuyen)
        VALUES
            (@AccountantRoleId, N'TUITION_VIEW'),
            (@AccountantRoleId, N'TUITION_CREATE'),
            (@AccountantRoleId, N'TUITION_UPDATE'),
            (@AccountantRoleId, N'QUAN_LY_HOC_PHI');

    IF @StudentRoleId IS NOT NULL
        INSERT INTO @DefaultGrants (VaiTroId, MaQuyen)
        VALUES
            (@StudentRoleId, N'GRADE_VIEW'),
            (@StudentRoleId, N'TUITION_VIEW');

    INSERT INTO dbo.VaiTro_Quyen (VaiTroId, QuyenId)
    SELECT grants.VaiTroId, permission.QuyenId
    FROM @DefaultGrants AS grants
    INNER JOIN dbo.Quyen AS permission
        ON permission.MaQuyen = grants.MaQuyen
    WHERE NOT EXISTS
    (
        SELECT 1
        FROM dbo.VaiTro_Quyen AS existing
        WHERE existing.VaiTroId = grants.VaiTroId
          AND existing.QuyenId = permission.QuyenId
    );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;