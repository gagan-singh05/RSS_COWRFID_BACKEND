
# from rest_framework import generics, status
# from rest_framework.response import Response
# from rest_framework.permissions import AllowAny

# from .models import RfidScan
# from .serializers import RfidScanSerializer
# from RSSDairy.sse import broadcaster


# class RfidScanListCreate(generics.ListCreateAPIView):
#     """
#     GET  /api/scans/   -> list all stored rows (one per UID), newest first
#     POST /api/scans/   -> upsert by uid, broadcast over SSE, return latest row
#     """
#     serializer_class = RfidScanSerializer
#     queryset = RfidScan.objects.all().order_by("-updated_at")

#     # 🔓 Open this endpoint (no auth => no CSRF for API calls)
#     authentication_classes: list = []
#     permission_classes = [AllowAny]

#     def create(self, request, *args, **kwargs):
#         uid = request.data.get("uid")
#         instance = RfidScan.objects.filter(uid=uid).first() if uid else None

#         # If instance exists => update; else => create
#         serializer = self.get_serializer(instance=instance, data=request.data)
#         serializer.is_valid(raise_exception=True)
#         obj = serializer.save()

#         out = RfidScanSerializer(obj).data
#         # Push to all SSE subscribers
#         try:
#             broadcaster.publish(out)
#         except Exception:
#             # Don't fail the API if streaming clients aren't connected
#             pass

#         return Response(out, status=status.HTTP_200_OK)


# class RfidScanDetail(generics.RetrieveUpdateDestroyAPIView):
#     """
#     GET    /api/scans/<pk>/   -> detail
#     PUT    /api/scans/<pk>/
#     PATCH  /api/scans/<pk>/
#     DELETE /api/scans/<pk>/
#     """
#     queryset = RfidScan.objects.all()
#     serializer_class = RfidScanSerializer

#     # 🔓 Open detail too (helpful for your standalone frontend)
#     authentication_classes: list = []
#     permission_classes = [AllowAny]
# RSSDairy/views.py
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from .models import RfidScan
from .serializers import RfidScanSerializer
from RSSDairy.sse import broadcaster

class RfidScanListCreate(generics.ListCreateAPIView):
    serializer_class = RfidScanSerializer
    queryset = RfidScan.objects.all().order_by("-updated_at")
    authentication_classes: list = []      # ✅ no session/JWT -> no CSRF
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        uid = request.data.get("uid")
        instance = RfidScan.objects.filter(uid=uid).first() if uid else None
        serializer = self.get_serializer(instance=instance, data=request.data)
        serializer.is_valid(raise_exception=True)

        # Determine block from name mapping: 'desh' -> 'A', 'bholu' -> 'B'
        name_val = serializer.validated_data.get("name") or request.data.get("name")
        block_override = None
        if name_val:
            try:
                name_clean = str(name_val).strip().lower()
            except Exception:
                name_clean = ""
            if name_clean == "desh":
                block_override = "A"
            elif name_clean == "bholu":
                block_override = "B"

        # If we determined a block, pass it to save() to enforce the mapping.
        if block_override is not None:
            obj = serializer.save(block=block_override)
        else:
            obj = serializer.save()
        out = RfidScanSerializer(obj).data
        try:
            broadcaster.publish(out)
        except Exception:
            pass
        return Response(out, status=status.HTTP_200_OK)

class RfidScanDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = RfidScan.objects.all()
    serializer_class = RfidScanSerializer
    authentication_classes: list = []      # ✅ open for your standalone HTML
    permission_classes = [AllowAny]
