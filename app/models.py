from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify
from django.db.models import Avg, Count

class SymbolicLanguage(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField()
    image = models.ImageField(upload_to='languages/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    avatar = models.ImageField(upload_to='avatars/', default='avatars/default.png')
    bio = models.TextField(blank=True, null=True)
    learned_languages = models.ManyToManyField(SymbolicLanguage, blank=True)
    is_manager = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.userprofile.save()

class Course(models.Model):
    DIFFICULTY_CHOICES = [('Beginner', 'Sơ cấp'), ('Intermediate', 'Trung cấp'), ('Advanced', 'Cao cấp')]
    CATEGORY_CHOICES = [('General', 'Chung'), ('Family', 'Gia đình'), ('Work', 'Công việc')]

    title = models.CharField(max_length=200)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='Beginner')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='General')
    duration = models.IntegerField(help_text="Duration in hours")

    def __str__(self):
        return self.title

    @property
    def reviews(self):
        return CourseReview.objects.filter(enrollment__course=self)

    @property
    def average_rating(self):
        avg = self.reviews.aggregate(Avg('rating'))['rating__avg']
        return avg if avg is not None else 0

    @property
    def review_count(self):
        return self.reviews.count()
    
    @property
    def student_count(self):
        return self.enrollments.count()

class Chapter(models.Model):
    course = models.ForeignKey(Course, related_name='chapters', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.course.title} - Chapter {self.order}: {self.title}"

class Exercise(models.Model):
    chapter = models.ForeignKey(Chapter, related_name='exercises', on_delete=models.CASCADE)
    question = models.TextField()
    order = models.PositiveIntegerField()
    video_guide = models.FileField(upload_to='exercise_guides/', null=True, blank=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Exercise {self.order} for {self.chapter.title}"

class Answer(models.Model):
    exercise = models.OneToOneField(Exercise, on_delete=models.CASCADE)
    correct_answer = models.CharField(max_length=255)

    def __str__(self):
        return f"Answer for {self.exercise.question[:30]}..."

class CourseEnrollment(models.Model):
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user_profile.user.username} enrolled in {self.course.title}"

    @property
    def progress_percentage(self):
        total_exercises = Exercise.objects.filter(chapter__course=self.course).count()
        if total_exercises == 0:
            return 0
        completed_count = UserExerciseCompletion.objects.filter(user=self.user_profile.user, exercise__chapter__course=self.course).count()
        return (completed_count / total_exercises) * 100

    class Meta:
        unique_together = ('user_profile', 'course')

class UserExerciseCompletion(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'exercise')

class CourseReview(models.Model):
    enrollment = models.ForeignKey(CourseEnrollment, on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Review for {self.enrollment.course.title} by {self.enrollment.user_profile.user.username}"

class Post(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posts')
    content = models.TextField()
    image = models.ImageField(upload_to='posts/', blank=True, null=True)
    video = models.FileField(upload_to='posts/videos', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

class Like(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='likes')
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'post')

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

class Conversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Conversation with {self.user.username}"

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"Message from {self.sender.username} at {self.timestamp}"

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
