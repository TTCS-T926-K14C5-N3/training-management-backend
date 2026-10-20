/* Sprint 5 assignments; migration id 016 follows the current maximum. */
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.Assignment', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.Assignment (
            AssignmentId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Assignment PRIMARY KEY,
            LopHocId INT NOT NULL,
            MonHocId INT NOT NULL,
            LichHocId INT NOT NULL,
            GiangVienId INT NOT NULL,
            TieuDe NVARCHAR(200) NOT NULL,
            MoTa NVARCHAR(MAX) NOT NULL,
            HanNop DATETIME2 NOT NULL,
            DiemToiDa DECIMAL(7,2) NOT NULL,
            ChoNopMuon BIT NOT NULL CONSTRAINT DF_Assignment_ChoNopMuon DEFAULT 0,
            TrangThai VARCHAR(20) NOT NULL CONSTRAINT DF_Assignment_TrangThai DEFAULT 'Draft',
            NgayTao DATETIME2 NOT NULL,
            NgayCapNhat DATETIME2 NOT NULL,
            CONSTRAINT CK_Assignment_Points CHECK (DiemToiDa > 0),
            CONSTRAINT CK_Assignment_Status CHECK (TrangThai IN ('Draft', 'Published')),
            CONSTRAINT FK_Assignment_ClassSubject FOREIGN KEY (LopHocId, MonHocId)
                REFERENCES dbo.LopHoc_MonHoc(LopHocId, MonHocId),
            CONSTRAINT FK_Assignment_Lesson FOREIGN KEY (LichHocId)
                REFERENCES dbo.LichHoc(LichHocId),
            CONSTRAINT FK_Assignment_Teacher FOREIGN KEY (GiangVienId)
                REFERENCES dbo.NguoiDung(NguoiDungId)
        );
        CREATE INDEX IX_Assignment_ClassSubjectStatus
            ON dbo.Assignment(LopHocId, MonHocId, TrangThai, HanNop);
    END;

    IF OBJECT_ID(N'dbo.AssignmentAttachment', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AssignmentAttachment (
            AttachmentId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_AssignmentAttachment PRIMARY KEY,
            AssignmentId INT NOT NULL,
            TenTepGoc NVARCHAR(255) NOT NULL,
            TenTepLuu VARCHAR(36) NOT NULL CONSTRAINT UQ_AssignmentAttachment_Stored UNIQUE,
            LoaiNoiDung VARCHAR(150) NULL,
            KichThuoc INT NOT NULL,
            NgayTao DATETIME2 NOT NULL,
            CONSTRAINT CK_AssignmentAttachment_Size CHECK (KichThuoc BETWEEN 0 AND 20971520),
            CONSTRAINT FK_AssignmentAttachment_Assignment FOREIGN KEY (AssignmentId)
                REFERENCES dbo.Assignment(AssignmentId)
        );
    END;

    IF OBJECT_ID(N'dbo.AssignmentSubmission', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AssignmentSubmission (
            SubmissionId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_AssignmentSubmission PRIMARY KEY,
            AssignmentId INT NOT NULL,
            HocVienId INT NOT NULL,
            VersionNumber INT NOT NULL,
            RepositoryUrl NVARCHAR(1000) NOT NULL,
            SubmittedAt DATETIME2 NOT NULL,
            SubmissionStatus VARCHAR(20) NOT NULL,
            CONSTRAINT UQ_AssignmentSubmission_Version UNIQUE (AssignmentId, HocVienId, VersionNumber),
            CONSTRAINT CK_AssignmentSubmission_Version CHECK (VersionNumber > 0),
            CONSTRAINT CK_AssignmentSubmission_Status CHECK (SubmissionStatus IN ('Submitted', 'Late')),
            CONSTRAINT FK_AssignmentSubmission_Assignment FOREIGN KEY (AssignmentId)
                REFERENCES dbo.Assignment(AssignmentId),
            CONSTRAINT FK_AssignmentSubmission_Student FOREIGN KEY (HocVienId)
                REFERENCES dbo.NguoiDung(NguoiDungId)
        );
        CREATE INDEX IX_AssignmentSubmission_Latest
            ON dbo.AssignmentSubmission(AssignmentId, HocVienId, VersionNumber DESC);
    END;

    IF OBJECT_ID(N'dbo.AssignmentSubmissionAttachment', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AssignmentSubmissionAttachment (
            AttachmentId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_AssignmentSubmissionAttachment PRIMARY KEY,
            SubmissionId INT NOT NULL,
            TenTepGoc NVARCHAR(255) NOT NULL,
            TenTepLuu VARCHAR(36) NOT NULL CONSTRAINT UQ_AssignmentSubmissionAttachment_Stored UNIQUE,
            LoaiNoiDung VARCHAR(150) NULL,
            KichThuoc INT NOT NULL,
            CONSTRAINT CK_AssignmentSubmissionAttachment_Size CHECK (KichThuoc BETWEEN 0 AND 20971520),
            CONSTRAINT FK_AssignmentSubmissionAttachment_Submission FOREIGN KEY (SubmissionId)
                REFERENCES dbo.AssignmentSubmission(SubmissionId)
        );
    END;

    IF OBJECT_ID(N'dbo.AssignmentGrade', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AssignmentGrade (
            GradeId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_AssignmentGrade PRIMARY KEY,
            SubmissionId INT NOT NULL,
            Diem DECIMAL(7,2) NOT NULL,
            NhanXet NVARCHAR(2000) NULL,
            GiangVienId INT NOT NULL,
            GradedAt DATETIME2 NOT NULL,
            CONSTRAINT CK_AssignmentGrade_Score CHECK (Diem >= 0),
            CONSTRAINT FK_AssignmentGrade_Submission FOREIGN KEY (SubmissionId)
                REFERENCES dbo.AssignmentSubmission(SubmissionId),
            CONSTRAINT FK_AssignmentGrade_Teacher FOREIGN KEY (GiangVienId)
                REFERENCES dbo.NguoiDung(NguoiDungId)
        );
        CREATE INDEX IX_AssignmentGrade_SubmissionDate
            ON dbo.AssignmentGrade(SubmissionId, GradedAt DESC, GradeId DESC);
    END;

    IF OBJECT_ID(N'dbo.AssignmentReopen', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AssignmentReopen (
            ReopenId INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_AssignmentReopen PRIMARY KEY,
            AssignmentId INT NOT NULL,
            HocVienId INT NOT NULL,
            GiangVienId INT NOT NULL,
            ReopenedAt DATETIME2 NOT NULL,
            LyDo NVARCHAR(1000) NOT NULL,
            CONSTRAINT FK_AssignmentReopen_Assignment FOREIGN KEY (AssignmentId)
                REFERENCES dbo.Assignment(AssignmentId),
            CONSTRAINT FK_AssignmentReopen_Student FOREIGN KEY (HocVienId)
                REFERENCES dbo.NguoiDung(NguoiDungId),
            CONSTRAINT FK_AssignmentReopen_Teacher FOREIGN KEY (GiangVienId)
                REFERENCES dbo.NguoiDung(NguoiDungId)
        );
        CREATE INDEX IX_AssignmentReopen_AssignmentStudent
            ON dbo.AssignmentReopen(AssignmentId, HocVienId, ReopenedAt DESC);
    END;

    IF NOT EXISTS (SELECT 1 FROM dbo.Quyen WHERE MaQuyen = N'ASSIGNMENT_VIEW')
        INSERT dbo.Quyen (MaQuyen, TenQuyen, MoTa)
        VALUES (N'ASSIGNMENT_VIEW', N'Xem bài tập', N'Xem bài tập và danh sách nộp bài trong phạm vi được phép.');
    IF NOT EXISTS (SELECT 1 FROM dbo.Quyen WHERE MaQuyen = N'ASSIGNMENT_CREATE')
        INSERT dbo.Quyen (MaQuyen, TenQuyen, MoTa)
        VALUES (N'ASSIGNMENT_CREATE', N'Tạo bài tập', N'Tạo và phát hành bài tập cho lớp được phân công.');
    IF NOT EXISTS (SELECT 1 FROM dbo.Quyen WHERE MaQuyen = N'ASSIGNMENT_SUBMIT')
        INSERT dbo.Quyen (MaQuyen, TenQuyen, MoTa)
        VALUES (N'ASSIGNMENT_SUBMIT', N'Nộp bài tập', N'Nộp bài và phiên bản nộp lại của bản thân.');
    IF NOT EXISTS (SELECT 1 FROM dbo.Quyen WHERE MaQuyen = N'ASSIGNMENT_GRADE')
        INSERT dbo.Quyen (MaQuyen, TenQuyen, MoTa)
        VALUES (N'ASSIGNMENT_GRADE', N'Chấm bài tập', N'Xem danh sách nộp, chấm và mở lại bài tập.');

    INSERT dbo.VaiTro_Quyen (VaiTroId, QuyenId)
    SELECT roles.VaiTroId, q.QuyenId
    FROM (VALUES (2, N'ASSIGNMENT_VIEW'), (2, N'ASSIGNMENT_SUBMIT'),
                 (3, N'ASSIGNMENT_VIEW'), (3, N'ASSIGNMENT_CREATE'), (3, N'ASSIGNMENT_GRADE'),
                 (4, N'ASSIGNMENT_VIEW'), (4, N'ASSIGNMENT_CREATE'), (4, N'ASSIGNMENT_GRADE'),
                 (7, N'ASSIGNMENT_VIEW'), (7, N'ASSIGNMENT_CREATE'), (7, N'ASSIGNMENT_GRADE'),
                 (8, N'ASSIGNMENT_VIEW'), (8, N'ASSIGNMENT_CREATE'),
                 (8, N'ASSIGNMENT_SUBMIT'), (8, N'ASSIGNMENT_GRADE')) AS roles(VaiTroId, MaQuyen)
    INNER JOIN dbo.Quyen q ON q.MaQuyen = roles.MaQuyen
    WHERE EXISTS (SELECT 1 FROM dbo.VaiTro vt WHERE vt.VaiTroId = roles.VaiTroId)
      AND NOT EXISTS (
          SELECT 1 FROM dbo.VaiTro_Quyen existing
          WHERE existing.VaiTroId = roles.VaiTroId AND existing.QuyenId = q.QuyenId
      );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;



