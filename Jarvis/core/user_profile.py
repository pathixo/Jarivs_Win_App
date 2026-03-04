"""
User Profile Module — Profile Management for Jarvis
=====================================================
Manages user identity (name, email, mobile, avatar) with local-first
storage and cloud-sync readiness.  Avatars are resized to 256×256 and
stored under DATA_DIR/avatars/.

Usage:
    from Jarvis.core.user_profile import get_profile_manager
    pm = get_profile_manager()
    user = pm.get_or_create_default_user()
    pm.update_profile(user["id"], display_name="Tony Stark")
"""

import logging
import os
import re
import shutil
import time
from typing import Optional

from Jarvis.config import DATA_DIR
from Jarvis.core.database import get_database

logger = logging.getLogger("jarvis.user_profile")

# ─────────────────────────── Constants ──────────────────────────────────────

AVATARS_DIR = os.path.join(DATA_DIR, "avatars")
DEFAULT_AVATAR = ""  # empty = use placeholder in UI

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

# ─────────────────────────── Singleton ──────────────────────────────────────

_instance: Optional["UserProfileManager"] = None


def get_profile_manager() -> "UserProfileManager":
    """Return the global UserProfileManager singleton."""
    global _instance
    if _instance is None:
        _instance = UserProfileManager()
    return _instance


# ─────────────────────────── UserProfileManager ─────────────────────────────

class UserProfileManager:
    """
    CRUD operations for user profiles.

    • Auto-creates a default user on first launch
    • Avatar images copied + resized to DATA_DIR/avatars/
    • Email validation via regex
    • Export/import for future cloud sync
    """

    def __init__(self):
        self._db = get_database()
        os.makedirs(AVATARS_DIR, exist_ok=True)
        # Cache the current user id
        self._current_user_id: Optional[str] = None

    # ── Core Operations ──────────────────────────────────────────────────

    def get_or_create_default_user(self) -> dict:
        """
        Return the default (and typically only) local user.
        Creates one with a new UUID if none exists.
        """
        row = self._db.fetch_one("SELECT * FROM users ORDER BY created_at ASC LIMIT 1")
        if row:
            self._current_user_id = row["id"]
            return dict(row)

        # First launch — create default user
        uid = self._db.new_id()
        now = time.time()
        self._db.execute(
            "INSERT INTO users (id, display_name, email, mobile, avatar_path, avatar_url, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, "", "", "", "", "", now, now),
        )
        self._current_user_id = uid
        logger.info("Created default user: %s", uid)
        return self.get_user(uid)

    def get_user(self, user_id: str) -> Optional[dict]:
        """Fetch a user by ID."""
        row = self._db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
        return dict(row) if row else None

    @property
    def current_user_id(self) -> str:
        """Return the current user's ID, creating if necessary."""
        if not self._current_user_id:
            self.get_or_create_default_user()
        return self._current_user_id

    def update_profile(
        self,
        user_id: str,
        display_name: Optional[str] = None,
        email: Optional[str] = None,
        mobile: Optional[str] = None,
    ) -> dict:
        """
        Update one or more profile fields.
        Returns the updated user dict.
        Raises ValueError for invalid email format.
        """
        user = self.get_user(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        if email is not None and email.strip():
            if not _EMAIL_RE.match(email.strip()):
                raise ValueError(f"Invalid email format: {email}")

        updates = []
        params = []
        if display_name is not None:
            updates.append("display_name = ?")
            params.append(display_name.strip())
        if email is not None:
            updates.append("email = ?")
            params.append(email.strip())
        if mobile is not None:
            updates.append("mobile = ?")
            params.append(mobile.strip())

        if updates:
            updates.append("updated_at = ?")
            params.append(time.time())
            params.append(user_id)
            self._db.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )
            logger.info("Updated profile for user %s", user_id)

        return self.get_user(user_id)

    # ── Avatar Management ────────────────────────────────────────────────

    def set_avatar(self, user_id: str, image_path: str) -> str:
        """
        Copy an image to the avatars directory, resize to 256×256.
        Returns the relative path under DATA_DIR.

        Uses Qt's QPixmap for resizing (no Pillow dependency).
        Falls back to raw copy if Qt is unavailable (e.g. headless).
        """
        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"Avatar image not found: {image_path}")

        ext = os.path.splitext(image_path)[1].lower() or ".png"
        if ext not in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
            ext = ".png"

        dest_filename = f"{user_id}{ext}"
        dest_path = os.path.join(AVATARS_DIR, dest_filename)

        # Try Qt resize
        try:
            from PyQt6.QtGui import QPixmap
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    256, 256,
                    aspectRatioMode=1,  # Qt.AspectRatioMode.KeepAspectRatio
                    transformMode=1,    # Qt.TransformationMode.SmoothTransformation
                )
                scaled.save(dest_path)
            else:
                shutil.copy2(image_path, dest_path)
        except ImportError:
            shutil.copy2(image_path, dest_path)

        # Store relative path
        rel_path = os.path.join("avatars", dest_filename)
        self._db.execute(
            "UPDATE users SET avatar_path = ?, updated_at = ? WHERE id = ?",
            (rel_path, time.time(), user_id),
        )
        logger.info("Avatar set for user %s: %s", user_id, rel_path)
        return rel_path

    def get_avatar_path(self, user_id: str) -> str:
        """
        Return the absolute path to the user's avatar.
        Returns empty string if no avatar is set.
        """
        user = self.get_user(user_id)
        if not user:
            return ""

        rel = user.get("avatar_path", "")
        if rel:
            abs_path = os.path.join(DATA_DIR, rel)
            if os.path.isfile(abs_path):
                return abs_path

        # Cloud fallback
        url = user.get("avatar_url", "")
        if url:
            return url  # UI can handle URLs

        return ""

    # ── Cloud Sync Helpers ───────────────────────────────────────────────

    def export_profile(self, user_id: str) -> dict:
        """Export user profile as a dict for cloud sync."""
        user = self.get_user(user_id)
        if not user:
            return {}
        return {
            "id": user["id"],
            "sync_token": user.get("sync_token", ""),
            "display_name": user["display_name"],
            "email": user["email"],
            "mobile": user["mobile"],
            "avatar_url": user.get("avatar_url", ""),
            "created_at": user["created_at"],
        }

    def import_profile(self, data: dict) -> None:
        """Import a profile from cloud data (upsert)."""
        uid = data.get("id")
        if not uid:
            return

        existing = self.get_user(uid)
        now = time.time()
        if existing:
            self._db.execute(
                "UPDATE users SET display_name=?, email=?, mobile=?, avatar_url=?, "
                "sync_token=?, updated_at=? WHERE id=?",
                (
                    data.get("display_name", ""),
                    data.get("email", ""),
                    data.get("mobile", ""),
                    data.get("avatar_url", ""),
                    data.get("sync_token", ""),
                    now,
                    uid,
                ),
            )
        else:
            self._db.execute(
                "INSERT INTO users (id, display_name, email, mobile, avatar_url, sync_token, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uid,
                    data.get("display_name", ""),
                    data.get("email", ""),
                    data.get("mobile", ""),
                    data.get("avatar_url", ""),
                    data.get("sync_token", ""),
                    data.get("created_at", now),
                    now,
                ),
            )

    # ── Stats ────────────────────────────────────────────────────────────

    def get_stats(self, user_id: str) -> dict:
        """Return profile statistics."""
        user = self.get_user(user_id)
        if not user:
            return {"member_since": "", "total_conversations": 0, "total_memories": 0}

        total_convos = self._db.fetch_scalar(
            "SELECT COUNT(*) FROM conversations WHERE user_id = ?",
            (user_id,),
            default=0,
        )
        total_memories = self._db.fetch_scalar(
            "SELECT COUNT(*) FROM memories WHERE user_id = ? AND active = 1",
            (user_id,),
            default=0,
        )

        import datetime
        created = user.get("created_at", 0)
        member_since = datetime.datetime.fromtimestamp(created).strftime("%B %d, %Y") if created else "Unknown"

        return {
            "member_since": member_since,
            "total_conversations": total_convos,
            "total_memories": total_memories,
        }
