from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """
    Tạo UserProfile khi một User mới được tạo, 
    hoặc chỉ cần lấy nó ra nếu nó đã tồn tại.
    """
    UserProfile.objects.get_or_create(user=instance)
