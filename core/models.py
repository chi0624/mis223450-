from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


# ---------- 課程 ----------
class Course(models.Model):
    name = models.CharField(max_length=200)
    date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


# ---------- 講次 ----------
class Lecture(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    title = models.CharField(max_length=100, blank=True, null=True)
    audio_file = models.FileField(upload_to='lectures/')
    transcript = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    quiz_generated = models.BooleanField(default=False)

    def __str__(self):
        return self.title or f"{self.course.name} 的講次"


# ---------- 題目 ----------
class Question(models.Model):
    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE)
    question_text = models.TextField()
    option_a = models.CharField(max_length=200, blank=True, null=True)
    option_b = models.CharField(max_length=200, blank=True, null=True)
    option_c = models.CharField(max_length=200, blank=True, null=True)
    option_d = models.CharField(max_length=200, blank=True, null=True)
    correct_answer = models.CharField(max_length=200)
    explanation = models.TextField()
    concept = models.CharField(max_length=100, default="未分類")
    question_type = models.CharField(
        max_length=20,
        choices=[('mcq', '選擇題'), ('tf', '是非題')],
        default='mcq'
    )

    def __str__(self):
        return self.question_text[:30]


# ---------- 學生 ----------
class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.name


# ---------- 學生作答 ----------
class Submission(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    student_answer = models.CharField(max_length=200)
    is_correct = models.BooleanField()
    submitted_at = models.DateTimeField(auto_now_add=True)


# ---------- 使用者角色 ----------
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(
        max_length=10,
        choices=[('teacher', '老師'), ('student', '學生')]
    )

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

    def is_teacher(self):
        return self.role == 'teacher'

    def is_student(self):
        return self.role == 'student'


# ---------- 自動建立 Profile ----------
@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance, role='student')  # 預設學生
    else:
        instance.profile.save()