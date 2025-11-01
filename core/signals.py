# core/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Profile, Student


@receiver(post_save, sender=User)
def create_profile_and_student(sender, instance, created, **kwargs):
    """
    自動在建立新 User 時，同步建立 Profile 與 Student。
    - 若 Profile 已存在（例如在 register 裡建立），則略過。
    - 預設角色為 student。
    """
    if created:
        # ✅ 避免重複建立 Profile（若 register() 已先創建）
        if not hasattr(instance, 'profile'):
            Profile.objects.create(user=instance, role='student')

        # ✅ 建立 Student（若不存在）
        if not Student.objects.filter(user=instance).exists():
            Student.objects.create(
                user=instance,
                name=instance.username,
                email=instance.email or f"{instance.username}@example.com"
            )


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """當 User 資料更新時，連動儲存 Profile"""
    if hasattr(instance, 'profile'):
        instance.profile.save()