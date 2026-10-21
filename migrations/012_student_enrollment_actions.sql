SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.StudentEnrollmentAction', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.StudentEnrollmentAction
        (
            ActionId INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            HocVienId INT NOT NULL,
            LopHocId INT NOT NULL,
            LopHocDichId INT NULL,
            LoaiThaoTac VARCHAR(30) NOT NULL,
            NgayHieuLuc DATE NOT NULL,
            LyDo NVARCHAR(1000) NOT NULL,
            NguoiThucHienId INT NOT NULL,
            NgayTao DATETIME2 NOT NULL,
            CONSTRAINT FK_StudentEnrollmentAction_HocVien
                FOREIGN KEY (HocVienId) REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_StudentEnrollmentAction_LopHoc
                FOREIGN KEY (LopHocId) REFERENCES dbo.LopHoc(LopHocId),
            CONSTRAINT FK_StudentEnrollmentAction_LopHocDich
                FOREIGN KEY (LopHocDichId) REFERENCES dbo.LopHoc(LopHocId),
            CONSTRAINT FK_StudentEnrollmentAction_NguoiThucHien
                FOREIGN KEY (NguoiThucHienId) REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT CK_StudentEnrollmentAction_LoaiThaoTac
                CHECK (LoaiThaoTac IN ('BaoLuu', 'ChuyenLop', 'ThoiHoc')),
            CONSTRAINT CK_StudentEnrollmentAction_LopDich
                CHECK ((LoaiThaoTac = 'ChuyenLop' AND LopHocDichId IS NOT NULL)
                    OR (LoaiThaoTac <> 'ChuyenLop' AND LopHocDichId IS NULL))
        );

        CREATE INDEX IX_StudentEnrollmentAction_HocVien_Ngay
            ON dbo.StudentEnrollmentAction(HocVienId, NgayHieuLuc);
        CREATE INDEX IX_StudentEnrollmentAction_Lop_HocVien_Ngay
            ON dbo.StudentEnrollmentAction(LopHocId, HocVienId, NgayHieuLuc);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;