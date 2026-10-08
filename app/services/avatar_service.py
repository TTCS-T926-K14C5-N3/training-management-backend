from io import BytesIO
import os
from pathlib import Path
import uuid
import warnings

from fastapi import HTTPException, status
from PIL import Image, ImageOps, UnidentifiedImageError


MAX_AVATAR_SIZE = 2 * 1024 * 1024
MAX_AVATAR_PIXELS = 20_000_000
AVATAR_SIZE = 256
AVATAR_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "uploads"
    / "avatars"
)


def avatar_path_for_user(user_id: int) -> Path:
    return AVATAR_DIRECTORY / f"{user_id}.jpg"


def avatar_url_for_user(user_id: int) -> str | None:
    avatar_path = avatar_path_for_user(user_id)

    if not avatar_path.is_file():
        return None

    return (
        f"/users/{user_id}/avatar"
        f"?v={avatar_path.stat().st_mtime_ns}"
    )


def save_avatar(user_id: int, image_data: bytes) -> Path:
    if len(image_data) > MAX_AVATAR_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Ảnh đại diện không được vượt quá 2 MB.",
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter(
                "error",
                Image.DecompressionBombWarning,
            )

            with Image.open(BytesIO(image_data)) as source:
                if source.format not in {"JPEG", "PNG"}:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Chỉ chấp nhận ảnh JPG hoặc PNG.",
                    )

                if source.width * source.height > MAX_AVATAR_PIXELS:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="Kích thước ảnh vượt quá giới hạn xử lý.",
                    )

                source.verify()

            with Image.open(BytesIO(image_data)) as source:
                image = ImageOps.exif_transpose(source)

                if "A" in image.getbands():
                    rgba_image = image.convert("RGBA")
                    image = Image.new(
                        "RGB",
                        rgba_image.size,
                        (255, 255, 255),
                    )
                    image.paste(
                        rgba_image,
                        mask=rgba_image.getchannel("A"),
                    )
                else:
                    image = image.convert("RGB")

                width, height = image.size
                side = min(width, height)
                left = (width - side) // 2
                top = (height - side) // 2
                image = image.crop(
                    (left, top, left + side, top + side)
                )
                image = image.resize(
                    (AVATAR_SIZE, AVATAR_SIZE),
                    Image.Resampling.LANCZOS,
                )

                output = BytesIO()
                image.save(
                    output,
                    format="JPEG",
                    quality=85,
                    optimize=True,
                )

    except HTTPException:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Kích thước ảnh vượt quá giới hạn xử lý.",
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tệp tải lên không phải ảnh JPG hoặc PNG hợp lệ.",
        ) from exc

    AVATAR_DIRECTORY.mkdir(parents=True, exist_ok=True)
    avatar_path = avatar_path_for_user(user_id)
    temporary_path = AVATAR_DIRECTORY / (
        f".{user_id}.{uuid.uuid4().hex}.tmp"
    )

    try:
        temporary_path.write_bytes(output.getvalue())
        os.replace(temporary_path, avatar_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return avatar_path
