SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.LopHoc_MonHoc_GiangVien', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LopHoc_MonHoc_GiangVien
        (
            LopHocId INT NOT NULL,
            MonHocId INT NOT NULL,
            GiangVienId INT NOT NULL,
            VaiTro NVARCHAR(20) NOT NULL,
            CONSTRAINT PK_LopHoc_MonHoc_GiangVien
                PRIMARY KEY (LopHocId, MonHocId, GiangVienId),
            CONSTRAINT CK_LopHoc_MonHoc_GiangVien_VaiTro
                CHECK (VaiTro IN (N'Chính', N'Trợ giảng')),
            CONSTRAINT FK_LopHoc_MonHoc_GiangVien_MonHoc
                FOREIGN KEY (LopHocId, MonHocId)
                REFERENCES dbo.LopHoc_MonHoc(LopHocId, MonHocId),
            CONSTRAINT FK_LopHoc_MonHoc_GiangVien_NguoiDung
                FOREIGN KEY (GiangVienId)
                REFERENCES dbo.NguoiDung(NguoiDungId)
        );
    END;

    IF NOT EXISTS
    (
        SELECT 1
        FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.LopHoc_MonHoc_GiangVien')
          AND name = N'UX_LopHoc_MonHoc_GiangVien_Chinh'
    )
        CREATE UNIQUE INDEX UX_LopHoc_MonHoc_GiangVien_Chinh
            ON dbo.LopHoc_MonHoc_GiangVien(LopHocId, MonHocId)
            WHERE VaiTro = N'Chính';

    INSERT INTO dbo.LopHoc_MonHoc_GiangVien
        (LopHocId, MonHocId, GiangVienId, VaiTro)
    SELECT class_subject.LopHocId, class_subject.MonHocId, class.GiangVienId, N'Chính'
    FROM dbo.LopHoc_MonHoc AS class_subject
    INNER JOIN dbo.LopHoc AS class ON class.LopHocId = class_subject.LopHocId
    WHERE class.GiangVienId IS NOT NULL
      AND NOT EXISTS
      (
          SELECT 1
          FROM dbo.LopHoc_MonHoc_GiangVien AS assignment
          WHERE assignment.LopHocId = class_subject.LopHocId
            AND assignment.MonHocId = class_subject.MonHocId
            AND assignment.VaiTro = N'Chính'
      );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
