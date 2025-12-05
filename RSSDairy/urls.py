from django.urls import path
from RSSDairy.views import RfidScanListCreate, RfidScanDetail, MissingCowsView
from RSSDairy.sse import stream_scans

urlpatterns = [
    path('scans/', RfidScanListCreate.as_view(), name='rfidscan-list'),
    path('scans/<int:pk>/', RfidScanDetail.as_view(), name='rfidscan-detail'),
    path('stream/', stream_scans, name='rfidscan-stream'),
    path("missing-cows/", MissingCowsView.as_view(), name="missing-cows"),
]
