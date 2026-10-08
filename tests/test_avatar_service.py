from io import BytesIO

import pytest
from fastapi import HTTPException
from PIL import Image

from app.services import avatar_service


def make_image(
    image_format: str = "PNG",
    size: tuple[int, int] = (400, 200),
) -> bytes:
    image = Image.new("RGB", size, (120, 80, 40))
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def test_save_avatar_crops_resizes_and_stores_jpeg(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        avatar_service,
        "AVATAR_DIRECTORY",
        tmp_path,
    )

    result = avatar_service.save_avatar(17, make_image())

    assert result == tmp_path / "17.jpg"
    with Image.open(result) as saved_image:
        assert saved_image.format == "JPEG"
        assert saved_image.size == (256, 256)


def test_save_avatar_accepts_jpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(
        avatar_service,
        "AVATAR_DIRECTORY",
        tmp_path,
    )

    result = avatar_service.save_avatar(18, make_image("JPEG"))

    assert result == tmp_path / "18.jpg"
    assert avatar_service.avatar_url_for_user(18).startswith(
        "/users/18/avatar?v="
    )


def test_save_avatar_rejects_unsupported_image(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        avatar_service,
        "AVATAR_DIRECTORY",
        tmp_path,
    )

    with pytest.raises(HTTPException) as error:
        avatar_service.save_avatar(17, make_image("WEBP"))

    assert error.value.status_code == 400
    assert list(tmp_path.iterdir()) == []


def test_save_avatar_rejects_oversized_upload(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        avatar_service,
        "AVATAR_DIRECTORY",
        tmp_path,
    )

    with pytest.raises(HTTPException) as error:
        avatar_service.save_avatar(
            17,
            b"x" * (avatar_service.MAX_AVATAR_SIZE + 1),
        )

    assert error.value.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_save_avatar_rejects_corrupt_image(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        avatar_service,
        "AVATAR_DIRECTORY",
        tmp_path,
    )

    with pytest.raises(HTTPException) as error:
        avatar_service.save_avatar(17, b"not an image")

    assert error.value.status_code == 400
    assert list(tmp_path.iterdir()) == []
