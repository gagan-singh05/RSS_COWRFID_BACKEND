
# from django.db import models

# class RfidScan(models.Model):
#     uid = models.CharField(max_length=50, unique=True)  # one row per tag
#     name = models.CharField(max_length=100)
#     block = models.CharField(max_length=10)
#     time = models.TimeField()   # from device (or make server-side if you prefer)
#     date = models.DateField()   # from device (or make server-side if you prefer)
#     updated_at = models.DateTimeField(auto_now=True)  # useful for ordering/display

#     def __str__(self):
#         return f"{self.name} ({self.uid}) - {self.date} {self.time}"
from django.db import models

class Block(models.Model):
    name = models.CharField(max_length=50, unique=True)
    
    def __str__(self):
        return self.name

class Cow(models.Model):
    uid = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    # Track where the cow currently is (based on last scan)
    last_seen_block = models.ForeignKey(Block, on_delete=models.SET_NULL, null=True, blank=True)
    last_seen_time = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.uid})"

class ScanSession(models.Model):
    # Only one session should be active at a time usually
    active_block = models.ForeignKey(Block, on_delete=models.CASCADE)
    start_time = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Session for {self.active_block} (Active: {self.is_active})"

class RfidScan(models.Model):
    uid = models.CharField(max_length=50)          # ❌ removed unique=True
    name = models.CharField(max_length=100)
    block = models.CharField(max_length=10)
    # NEW: direction of movement
    direction = models.CharField(
        max_length=3,
        choices=[("IN", "IN"), ("OUT", "OUT")],
        default="OUT",    # default for old rows
    )
    time = models.TimeField()                      # from device
    date = models.DateField()                      # from device
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.uid}) - {self.date} {self.time} [{self.direction}]"
