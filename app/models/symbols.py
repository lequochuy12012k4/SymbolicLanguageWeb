from django.db import models
from django.utils.text import slugify

class SymbolCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Tên danh mục")
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True, verbose_name="Mô tả")

    class Meta:
        verbose_name = "Danh mục Ký hiệu"
        verbose_name_plural = "Các danh mục Ký hiệu"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

class Symbol(models.Model):
    category = models.ForeignKey(SymbolCategory, related_name='symbols', on_delete=models.CASCADE, verbose_name="Danh mục")
    name = models.CharField(max_length=100, verbose_name="Tên ký hiệu")
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    image = models.ImageField(upload_to='symbols/images/', help_text='An image representing the symbol.')
    video = models.FileField(upload_to='symbol_videos/', verbose_name="Video minh họa")
    description = models.TextField(blank=True, verbose_name="Mô tả chi tiết")

    class Meta:
        verbose_name = "Ký hiệu"
        verbose_name_plural = "Các ký hiệu"
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
