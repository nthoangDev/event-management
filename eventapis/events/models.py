from django.db import models
from django.contrib.auth.models import AbstractUser
from ckeditor.fields import RichTextField
from cloudinary.models import CloudinaryField


# ------------------ USERS & ROLES ------------------
class User(AbstractUser):
    avatar = CloudinaryField(null=True)
    is_organizer = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.username} ({self.email})"


class OrganizerRequest(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    info = models.TextField()
    status = models.CharField(max_length=10,
                              choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
                              default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Organizer Request: {self.user.username} - {self.status}"


# ------------------ BASE MODEL ------------------
class BaseModel(models.Model):
    active = models.BooleanField(default=True)
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-id']


# ------------------ EVENTS ------------------
class Category(BaseModel):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return f"Category: {self.name}"


class Event(BaseModel):
    organizer = models.ForeignKey(User, on_delete=models.PROTECT)
    name = models.CharField(max_length=255)
    description = RichTextField(null=True)
    event_time = models.DateTimeField()
    location = models.CharField(max_length=255)
    ticket_price = models.DecimalField(max_digits=10, decimal_places=2)
    image = CloudinaryField(null=True)
    video_url = models.URLField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=[('pending', 'Pending'), ('approved', 'Approved'), ('hot', 'Hot'),
                                                      ('blocked', 'Blocked')], default='pending')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, null=True, related_name='events')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Event: {self.name} | Organizer: {self.organizer.username} | Date: {self.event_time.strftime('%Y-%m-%d %H:%M')}"


class EventTag(BaseModel):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    tag = models.CharField(max_length=50)

    def __str__(self):
        return f"Tag: {self.tag} for {self.event.name}"


# ------------------ BOOKING ------------------
class Ticket(BaseModel):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    ticket_type = models.CharField(max_length=10, choices=[('regular', 'Regular'), ('VIP', 'VIP')])
    status = models.CharField(max_length=15,
                              choices=[('pending', 'Pending'), ('booked', 'Booked'), ('cancelled', 'Cancelled')],
                              default='pending')
    qr_code = models.CharField(max_length=100, unique=True)
    expires_at = models.DateTimeField()  # Hạn 30 phút hoặc 3 phút

    def __str__(self):
        return f"Ticket: {self.ticket_type} | {self.event.name} | User: {self.user.username} | Status: {self.status}"


class Payment(BaseModel):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE)

    method = models.CharField(max_length=20,
                              choices=[('Momo', 'Momo'), ('ZaloPay', 'ZaloPay'), ('Credit Card', 'Credit Card')])
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=[('completed', 'Completed'), ('failed', 'Failed')])

    def __str__(self):
        return f"Payment: {self.amount} | Method: {self.method} | Status: {self.status}"


# ------------------ INTERACTIONS ------------------
class Like(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    def __str__(self):
        return f"Like: {self.event.name} by {self.user.username}"


class Interest(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    def __str__(self):
        return f"Interest: {self.user.username} in {self.event.name}"


class Review(BaseModel):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    rating = models.IntegerField(choices=[(i, str(i)) for i in range(1, 6)])
    comment = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Review: {self.rating} | {self.event.name} by {self.user.username}"


class Notification(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    message = models.TextField()
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification: {self.message[:30]}... | User: {self.user.username} | Read: {self.is_read}"
