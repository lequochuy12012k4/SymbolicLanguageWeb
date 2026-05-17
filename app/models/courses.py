from django.db import models
from django.contrib.auth.models import User
from django.db.models import Avg

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
    user_profile = models.ForeignKey('app.UserProfile', on_delete=models.CASCADE)
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
