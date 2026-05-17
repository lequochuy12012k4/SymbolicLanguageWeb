from django.db import models

class AIModel(models.Model):
    name = models.CharField(max_length=100, unique=True)
    file_path = models.CharField(max_length=255)
    is_active = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {'Active' if self.is_active else 'Inactive'}"

    def save(self, *args, **kwargs):
        if self.is_active:
            AIModel.objects.filter(is_active=True).update(is_active=False)
        super(AIModel, self).save(*args, **kwargs)

class AIProvider(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Tên nhà cung cấp")
    api_key = models.CharField(max_length=255, verbose_name="API Key")
    is_active = models.BooleanField(default=False, verbose_name="Kích hoạt")

    class Meta:
        verbose_name = "Nhà cung cấp AI"
        verbose_name_plural = "Các nhà cung cấp AI"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_active:
            AIProvider.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

class APIModel(models.Model):
    provider = models.ForeignKey(AIProvider, on_delete=models.CASCADE, related_name='api_models', verbose_name="Nhà cung cấp")
    model_name = models.CharField(max_length=100, verbose_name="Tên Model")
    is_active = models.BooleanField(default=False, verbose_name="Kích hoạt")

    class Meta:
        verbose_name = "Model API"
        verbose_name_plural = "Các Model API"
        unique_together = ('provider', 'model_name')

    def __str__(self):
        return f"{self.provider.name} - {self.model_name}"

    def save(self, *args, **kwargs):
        if self.is_active:
            APIModel.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)
